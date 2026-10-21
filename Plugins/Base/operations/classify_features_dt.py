#!/usr/bin/env python3
"""
Decision Tree Feature Classification (headless)

Reads per-file extracted features (tsi_features.json) and runs all eligible
Decision Tree models found in a models folder. Produces per-file predictions
and a batch consensus across files.

- No GUI, no dashboard messaging unless status_callback is wired by the runner.
- Writes classification_report.json next to artifacts for later consumption.
- If models are missing/invalid, still writes classification_report.json with
  status="skipped" so the SOI chain can report an unclassified result instead
  of failing because the report is absent.

Stop semantics
--------------
- If stop is requested, exit promptly and DO NOT write classification_report.json.
"""

import ast
import asyncio
import json
import logging
import os
import pickle
import sys
import time
import uuid
from typing import Any, Dict, List, Optional, Union


PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FISSURE_REPO_ROOT = os.path.abspath(os.path.join(PLUGIN_ROOT, "..", ".."))

for path in (FISSURE_REPO_ROOT, PLUGIN_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

import numpy as np

try:
    from fissure.utils.plugins.operations import Operation
except ImportError:
    if FISSURE_REPO_ROOT not in sys.path:
        sys.path.insert(0, FISSURE_REPO_ROOT)

    if PLUGIN_ROOT not in sys.path:
        sys.path.insert(0, PLUGIN_ROOT)

    from fissure.utils.plugins.operations import Operation


def _default_models_folder() -> str:
    return os.path.join(
        PLUGIN_ROOT,
        "resources",
        "decision_tree_models",
    )


def _legacy_models_folder() -> str:
    return os.path.join(
        os.path.dirname(__file__),
        "decision_tree_models",
    )


def _resolve_models_folder(models_folder: Optional[str]) -> str:
    if models_folder:
        return str(models_folder)

    preferred = _default_models_folder()
    if os.path.isdir(preferred):
        return preferred

    legacy = _legacy_models_folder()
    if os.path.isdir(legacy):
        return legacy

    return preferred


def _to_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value

    if value is None:
        return default

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        v = value.strip().lower()

        if v in {"true", "1", "yes", "y", "on", "enabled"}:
            return True

        if v in {"false", "0", "no", "n", "off", "disabled"}:
            return False

    return default


def _read_model_details(txt_path: str) -> Dict[str, Any]:
    """
    Parses a model .txt file:
      Technique: Decision Tree
      Features: [...]
      Truth Categories: [...]
    """
    details: Dict[str, Any] = {"path": txt_path}

    with open(txt_path, "r", encoding="utf-8") as f:
        blob = f.read()

    details["raw"] = blob

    for line in blob.splitlines():
        if line.startswith("Technique: "):
            details["technique"] = line.split("Technique: ", 1)[1].strip()
        elif line.startswith("Features: "):
            try:
                details["features"] = ast.literal_eval(
                    line.split("Features: ", 1)[1].strip()
                )
            except Exception:
                details["features"] = []
        elif line.startswith("Truth Categories: "):
            details["truth_categories"] = line.split("Truth Categories: ", 1)[1].strip()

    if "features" not in details:
        details["features"] = []

    return details


def _load_feature_rows(features_json_path: str) -> List[Dict[str, Any]]:
    with open(features_json_path, "r", encoding="utf-8") as f:
        rows = json.load(f)

    if not isinstance(rows, list):
        raise ValueError("features file must be a JSON list")

    return rows


def _eligible_models(
    model_details: List[Dict[str, Any]],
    available_features: List[str],
) -> List[Dict[str, Any]]:
    avail = set(available_features)
    out: List[Dict[str, Any]] = []

    for md in model_details:
        req = md.get("features", [])
        if isinstance(req, list) and req and set(req).issubset(avail):
            out.append(md)

    return out


def _safe_float(v: Any) -> float:
    try:
        if v is None:
            return float("nan")
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, (np.integer, np.floating)):
            return float(v)
        return float(v)
    except Exception:
        return float("nan")


def _find_model_file(
    models_folder: str,
    model_stem: str,
) -> Optional[str]:
    """Resolve the persisted model file for a model sidecar."""
    candidates = [
        os.path.join(models_folder, model_stem + ".pkl"),
        os.path.join(models_folder, model_stem + ".pickle"),
        os.path.join(models_folder, model_stem + ".h5"),
    ]

    for path in candidates:
        if os.path.isfile(path):
            return path

    return None


class OperationMain(Operation):
    def __init__(
        self,
        node_uid: str = "",
        logger: logging.Logger = logging.getLogger(__name__),
        alert_callback=None,
        tak_cot_callback=None,
        status_callback=None,
        artifact_manager=None,
        source_id: str = "",
        operation_id: str = "",
        destination: str = "Local Results",
        description: str = "",
        input_source: str = "",
        input_soi_id: str = "",
        input_soi_key: str = "",
        input_soi_frequency_mhz: Any = None,
        source_artifact_id: str = "",
        source_artifact_ids: Optional[List[str]] = None,
        managed_input: Optional[Dict[str, Any]] = None,
        features_path: str = "",
        folder: Optional[str] = None,
        models_folder: Optional[str] = None,
        features_file: str = "tsi_features.json",
        min_models: int = 1,
        use_batch_consensus: Union[str, bool] = True,
        selected_models: Optional[List[str]] = None,
        library_candidates: Optional[List[Dict[str, Any]]] = None,
    ):
        super().__init__(
            node_uid=node_uid,
            logger=logger,
            alert_callback=alert_callback,
            tak_cot_callback=tak_cot_callback,
            status_callback=status_callback,
            artifact_manager=artifact_manager,
        )
        if operation_id:
            self.opid = str(operation_id)
        self.source_id = str(source_id or node_uid or "sensor_node")
        self.destination = str(destination or "Local Results").strip()
        self.description = str(description or "Classification analysis results").strip()
        self.input_source = str(input_source or "").strip()
        self.input_soi_id = str(input_soi_id or "").strip()
        self.input_soi_key = str(input_soi_key or "").strip()
        self.input_soi_frequency_mhz = input_soi_frequency_mhz
        self.source_artifact_id = str(source_artifact_id or "").strip()
        self.source_artifact_ids = [
            str(value or "").strip()
            for value in (source_artifact_ids or [])
            if str(value or "").strip()
        ]
        self.managed_input = (
            dict(managed_input)
            if isinstance(managed_input, dict)
            else {}
        )
        self.features_path = str(features_path or "").strip()
        self.folder = folder
        self.models_folder = _resolve_models_folder(models_folder)
        self.features_file = str(features_file or "tsi_features.json")
        self.min_models = int(min_models)
        self.use_batch_consensus = _to_bool(use_batch_consensus, True)
        self.selected_models = (
            [
                str(value or "").strip()
                for value in selected_models
                if str(value or "").strip()
            ]
            if isinstance(selected_models, list)
            else None
        )
        self.library_candidates = [
            dict(value)
            for value in (library_candidates or [])
            if isinstance(value, dict)
        ]
        self.artifact_id = ""
        self.report_payload: Dict[str, Any] = {}

    def _resolve_managed_features_path(self, managed_input: Dict[str, Any]) -> str:
        if self.artifact_manager is None:
            raise RuntimeError("Artifact manager unavailable for managed classifier input")

        artifacts = managed_input.get("artifacts", []) if isinstance(managed_input, dict) else []
        if not isinstance(artifacts, list):
            artifacts = []

        if not artifacts:
            artifact_ids = managed_input.get("artifact_ids", []) if isinstance(managed_input, dict) else []
            if not isinstance(artifact_ids, list):
                artifact_ids = [artifact_ids]
            artifacts = [
                {"artifact_id": str(artifact_id or "").strip()}
                for artifact_id in artifact_ids
                if str(artifact_id or "").strip()
            ]

        for request in artifacts:
            if not isinstance(request, dict):
                continue

            artifact_id = str(request.get("artifact_id") or "").strip()
            if not artifact_id:
                continue

            artifact = self.artifact_manager.get_artifact(artifact_id)
            if artifact is None:
                continue

            selected = request.get("selected_files", [])
            if not isinstance(selected, list):
                selected = []

            requested_ids = {
                str(item.get("file_id") or "").strip()
                for item in selected
                if isinstance(item, dict) and str(item.get("file_id") or "").strip()
            }
            requested_names = {
                str(item.get("name") or "").strip()
                for item in selected
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            }
            requested_roles = {
                str(item.get("role") or "").strip()
                for item in selected
                if isinstance(item, dict) and str(item.get("role") or "").strip()
            }
            has_selection = bool(requested_ids or requested_names or requested_roles)

            for artifact_file in artifact.files:
                if has_selection:
                    matches_selection = (
                        artifact_file.id in requested_ids
                        or artifact_file.name in requested_names
                        or artifact_file.relative_path in requested_names
                        or artifact_file.role in requested_roles
                    )
                    if not matches_selection:
                        continue

                if (
                    artifact_file.name == self.features_file
                    or os.path.basename(artifact_file.relative_path) == self.features_file
                    or artifact_file.role == "feature_results"
                ):
                    path = self.artifact_manager.resolve_artifact_file_path(
                        artifact_id,
                        artifact_file.id,
                    )
                    if path and os.path.isfile(path):
                        self.logger.info(
                            "Resolved classifier Feature Analysis input: artifact_id=%s file=%s",
                            artifact_id,
                            artifact_file.name,
                        )
                        return path

            for artifact_file in artifact.files:
                if (
                    artifact_file.name == self.features_file
                    or os.path.basename(artifact_file.relative_path) == self.features_file
                    or artifact_file.role == "feature_results"
                ):
                    path = self.artifact_manager.resolve_artifact_file_path(
                        artifact_id,
                        artifact_file.id,
                    )
                    if path and os.path.isfile(path):
                        self.logger.info(
                            "Resolved classifier Feature Analysis input: artifact_id=%s file=%s",
                            artifact_id,
                            artifact_file.name,
                        )
                        return path

        raise FileNotFoundError(
            "No tsi_features.json member found in selected Feature Analysis Artifact"
        )
    
    def _resolve_paths(self, params: Dict[str, Any]) -> tuple:
        managed_input = params.get("managed_input", self.managed_input)
        managed_input = dict(managed_input) if isinstance(managed_input, dict) else {}
        features_path = str(params.get("features_path", self.features_path) or "").strip()
        folder = params.get("folder", self.folder)
        features_file = str(params.get("features_file", self.features_file) or "tsi_features.json")

        if managed_input:
            features_path = self._resolve_managed_features_path(managed_input)
        elif features_path:
            features_path = os.path.abspath(features_path)
        elif folder:
            features_path = os.path.join(str(folder), features_file)
        else:
            raise ValueError("Classifier requires managed Artifact input, features_path, or folder")

        legacy_in_place = bool(folder and not managed_input and not params.get("features_path") and not self.features_path)
        if legacy_in_place:
            output_folder = os.path.abspath(str(folder))
        elif self.artifact_manager is not None:
            _, output_folder = self.artifact_manager.create_operation_dir(self.opid)
        else:
            output_folder = os.path.dirname(features_path)
        os.makedirs(output_folder, exist_ok=True)
        return features_path, output_folder

    async def run(self) -> None:
        params: Dict[str, Any] = getattr(self, "parameters", {}) or {}
        models_folder = _resolve_models_folder(
            params.get("models_folder", self.models_folder)
        )
        min_models = int(params.get("min_models", self.min_models))
        use_batch_consensus = _to_bool(
            params.get("use_batch_consensus", self.use_batch_consensus),
            True,
        )
        destination = str(
            params.get("destination", self.destination)
            or "Local Results"
        ).strip()
        description = str(
            params.get("description", self.description)
            or "Classification analysis results"
        ).strip()
        library_candidates = params.get(
            "library_candidates",
            self.library_candidates,
        )
        library_candidates = (
            [
                dict(value)
                for value in library_candidates
                if isinstance(value, dict)
            ]
            if isinstance(library_candidates, list)
            else []
        )
        source_artifact_ids = params.get(
            "source_artifact_ids",
            self.source_artifact_ids,
        )
        if not isinstance(source_artifact_ids, list):
            source_artifact_ids = [source_artifact_ids]
        source_artifact_ids = [
            str(value or "").strip()
            for value in source_artifact_ids
            if str(value or "").strip()
        ]

        selected_models_value = params.get(
            "selected_models",
            self.selected_models,
        )
        if selected_models_value is None:
            selected_model_set = None
        else:
            if not isinstance(selected_models_value, list):
                selected_models_value = [selected_models_value]
            selected_model_set = {
                str(value or "").strip()
                for value in selected_models_value
                if str(value or "").strip()
            }

        started_at = time.time()

        if destination not in {"Local Results", "Artifact"}:
            raise ValueError(
                f"Unsupported Classifier destination: {destination}"
            )

        features_path, output_folder = self._resolve_paths(params)
        out_path = os.path.join(
            output_folder,
            "classification_report.json",
        )

        if getattr(self, "status_callback", None):
            try:
                await self.status_callback(
                    "Running: Classifying Features"
                )
            except Exception:
                self.logger.exception(
                    "status_callback failed: set running"
                )

        if self._stop:
            return

        if not os.path.isfile(features_path):
            self._write_report(
                out_path,
                self._base_report(
                    "skipped",
                    "missing_features_file",
                    features_path,
                    models_folder,
                    min_models,
                    use_batch_consensus,
                    library_candidates,
                    started_at,
                ),
            )
            return

        try:
            with open(features_path, "r", encoding="utf-8") as handle:
                rows = json.load(handle)
        except Exception as error:
            self._write_report(
                out_path,
                self._base_report(
                    "skipped",
                    f"invalid_features_file:{error!r}",
                    features_path,
                    models_folder,
                    min_models,
                    use_batch_consensus,
                    library_candidates,
                    started_at,
                ),
            )
            return

        if not isinstance(rows, list):
            self._write_report(
                out_path,
                self._base_report(
                    "skipped",
                    "features_file_not_list",
                    features_path,
                    models_folder,
                    min_models,
                    use_batch_consensus,
                    library_candidates,
                    started_at,
                ),
            )
            return

        available_features = []
        for row in rows:
            features = (
                row.get("features", {})
                if isinstance(row, dict)
                else {}
            )
            if not isinstance(features, dict):
                continue
            for name in features:
                if name not in available_features:
                    available_features.append(name)
        available_features = sorted(available_features)

        discovered_models: List[Dict[str, Any]] = []
        if os.path.isdir(models_folder):
            for name in sorted(os.listdir(models_folder), key=str.lower):
                if self._stop:
                    return
                if not name.lower().endswith(".txt"):
                    continue

                try:
                    details = _read_model_details(
                        os.path.join(models_folder, name)
                    )
                except Exception as error:
                    self.logger.warning(
                        f"Failed reading model details {name}: {error!r}"
                    )
                    continue

                if details.get("technique") != "Decision Tree":
                    continue

                discovered_models.append(details)

        if selected_model_set is None:
            model_details = list(discovered_models)
        else:
            model_details = []
            for details in discovered_models:
                model_stem = os.path.splitext(
                    os.path.basename(details.get("path") or "")
                )[0]
                if model_stem in selected_model_set:
                    model_details.append(details)

        selected_model_names = sorted(
            os.path.splitext(
                os.path.basename(details.get("path") or "")
            )[0]
            for details in model_details
            if str(details.get("path") or "").strip()
        )

        eligible_any = _eligible_models(
            model_details,
            available_features,
        )
        per_file: List[Dict[str, Any]] = []

        for row in rows:
            if self._stop:
                return

            file_name = row.get("file") if isinstance(row, dict) else ""
            features = (
                row.get("features", {})
                if isinstance(row, dict)
                else {}
            )

            if not isinstance(features, dict) or not features:
                per_file.append(
                    {
                        "file": file_name,
                        "error": "missing_features",
                        "models_used": 0,
                        "votes": {},
                        "vote_counts": {},
                        "consensus": {
                            "label": None,
                            "confidence": None,
                        },
                        "skipped": [],
                    }
                )
                continue

            file_eligible = _eligible_models(
                model_details,
                sorted(features.keys()),
            )
            votes: Dict[str, str] = {}
            skipped: List[Dict[str, Any]] = []

            for details in file_eligible:
                if self._stop:
                    return

                model_stem = os.path.splitext(
                    os.path.basename(details["path"])
                )[0]
                model_path = _find_model_file(
                    models_folder,
                    model_stem,
                )
                if not model_path:
                    skipped.append(
                        {
                            "model": model_stem,
                            "reason": "missing_model_file",
                        }
                    )
                    continue

                required_features = details.get("features", [])
                if (
                    not isinstance(required_features, list)
                    or not required_features
                ):
                    skipped.append(
                        {
                            "model": model_stem,
                            "reason": "missing_required_features",
                        }
                    )
                    continue

                values = np.array(
                    [[
                        _safe_float(features.get(feature))
                        for feature in required_features
                    ]],
                    dtype=np.float64,
                )

                try:
                    with open(model_path, "rb") as handle:
                        classifier = pickle.load(handle)
                    votes[model_stem] = str(
                        classifier.predict(values)[0]
                    )
                except Exception as error:
                    skipped.append(
                        {
                            "model": model_stem,
                            "reason": "predict_failed",
                            "error": repr(error),
                        }
                    )

            vote_counts: Dict[str, int] = {}
            for label in votes.values():
                vote_counts[label] = vote_counts.get(label, 0) + 1

            models_used = len(votes)
            if vote_counts:
                best_label, best_votes = max(
                    vote_counts.items(),
                    key=lambda item: item[1],
                )
                confidence = (
                    best_votes / models_used
                    if models_used
                    else None
                )
            else:
                best_label = None
                confidence = None

            per_file.append(
                {
                    "file": file_name,
                    "models_used": models_used,
                    "votes": votes,
                    "vote_counts": vote_counts,
                    "consensus": {
                        "label": best_label,
                        "confidence": confidence,
                    },
                    "skipped": skipped,
                }
            )

        batch = {
            "label": None,
            "confidence": None,
            "files_used": 0,
            "vote_counts": {},
        }

        if use_batch_consensus and not self._stop:
            batch_counts: Dict[str, int] = {}
            used_files = 0

            for per_file_result in per_file:
                label = per_file_result.get(
                    "consensus",
                    {},
                ).get("label")
                if not label:
                    continue
                batch_counts[label] = batch_counts.get(label, 0) + 1
                used_files += 1

            if batch_counts:
                batch_label, batch_votes = max(
                    batch_counts.items(),
                    key=lambda item: item[1],
                )
                batch = {
                    "label": batch_label,
                    "confidence": (
                        batch_votes / used_files
                        if used_files
                        else None
                    ),
                    "files_used": used_files,
                    "vote_counts": batch_counts,
                }

        if self._stop:
            return

        models_used_total = sum(
            int(result.get("models_used", 0))
            for result in per_file
        )

        if selected_model_set is not None and not selected_model_names:
            status = "unclassified"
            reason = "no_models_selected"
        elif batch.get("label"):
            status = "classified"
            reason = ""
        elif models_used_total > 0:
            status = "unclassified"
            reason = "no_batch_consensus"
        elif len(eligible_any) < min_models:
            status = "unclassified"
            reason = "insufficient_eligible_models"
        else:
            status = "unclassified"
            reason = "no_model_votes"

        completed_at = time.time()
        reserved_artifact_id = (
            str(uuid.uuid4())
            if destination == "Artifact"
            else ""
        )
        report = {
            "operation": "classify_features_dt_v2",
            "workflow": "classifier",
            "kind": "classification_analysis",
            "role": "classification_analysis_v1",
            "status": status,
            "reason": reason,
            "node_uid": str(
                params.get("node_uid")
                or self.node_uid
                or ""
            ),
            "source_id": str(
                params.get("source_id")
                or self.source_id
                or ""
            ),
            "operation_id": self.opid,
            "destination": destination,
            "description": description,
            "input_source": str(
                params.get("input_source", self.input_source)
                or ""
            ),
            "input_soi_id": str(
                params.get("input_soi_id", self.input_soi_id)
                or ""
            ),
            "input_soi_key": str(
                params.get("input_soi_key", self.input_soi_key)
                or ""
            ),
            "input_soi_frequency_mhz": params.get(
                "input_soi_frequency_mhz",
                self.input_soi_frequency_mhz,
            ),
            "source_artifact_id": (
                source_artifact_ids[0]
                if len(source_artifact_ids) == 1
                else ""
            ),
            "source_artifact_ids": source_artifact_ids,
            "features_file": os.path.basename(features_path),
            "available_features": available_features,
            "models_folder": models_folder,
            "models_discovered": len(discovered_models),
            "models_selected": selected_model_names,
            "models_selected_count": len(selected_model_names),
            "models_eligible_any": len(eligible_any),
            "min_models": min_models,
            "use_batch_consensus": use_batch_consensus,
            "per_file": per_file,
            "batch": batch,
            "library_candidates": library_candidates,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_s": max(0.0, completed_at - started_at),
            "artifact_id": reserved_artifact_id,
            "created_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(),
            ),
        }
        self._write_report(
            out_path,
            report,
        )

        if destination == "Artifact":
            if self.artifact_manager is None:
                raise RuntimeError(
                    "Artifact manager unavailable for Classification Artifact output"
                )

            relations = [
                ("artifact", artifact_id, "derived_from")
                for artifact_id in source_artifact_ids
            ]
            artifact_id = self.artifact_manager.create_artifact(
                source_id=str(
                    params.get("source_id")
                    or self.source_id
                    or self.node_uid
                    or "sensor_node"
                ),
                operation_id=self.opid,
                files=[out_path],
                name=description or "Classification Analysis",
                artifact_type="classification_analysis",
                metadata=report,
                relations=relations,
                file_metadata={
                    out_path: {
                        "role": "classification_results",
                        "content_type": "application/json",
                    }
                },
                artifact_id=reserved_artifact_id,
            )
            self.artifact_id = str(
                getattr(artifact_id, "id", artifact_id)
                or reserved_artifact_id
            )

        self.report_payload = report
        
    def _base_report(self, status: str, reason: str, features_path: str, models_folder: str, min_models: int, use_batch_consensus: bool, library_candidates: list, started_at: float) -> Dict[str, Any]:
        return {
            "operation": "classify_features_dt_v2", "workflow": "classifier", "kind": "classification_analysis",
            "status": status, "reason": reason, "operation_id": self.opid, "features_path": features_path,
            "models_folder": models_folder, "models_discovered": 0, "models_eligible_any": 0, "min_models": min_models,
            "use_batch_consensus": use_batch_consensus, "library_candidates": library_candidates, "per_file": [],
            "batch": {"label": None, "confidence": None, "files_used": 0, "vote_counts": {}},
            "started_at": started_at, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def _write_report(self, out_path: str, report: Dict[str, Any]) -> None:
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, allow_nan=True)
            self.logger.info(f"Wrote classification report: {out_path}")
        except Exception as e:
            self.logger.warning(f"Failed writing classification_report.json: {e!r}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def _main():
        op = OperationMain(
            node_uid="test-node",
            logger=logging.getLogger("dt_classify_test"),
            folder="/tmp/some_artifact_folder",
        )
        await op.run()

    asyncio.run(_main())