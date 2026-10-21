"""Basic IQ analysis for the Signal Analysis Inspection workspace."""

import logging
import math
import os
from typing import Callable, Union

import numpy as np

from fissure.utils.plugins.operations import Operation


_SIGMF_TYPES = {
    "cf32_le": (np.dtype("<c8"), False),
    "cf32_be": (np.dtype(">c8"), False),
    "cf64_le": (np.dtype("<c16"), False),
    "cf64_be": (np.dtype(">c16"), False),
    "ci16_le": (np.dtype("<i2"), True),
    "ci16_be": (np.dtype(">i2"), True),
    "cu16_le": (np.dtype("<u2"), True),
    "cu16_be": (np.dtype(">u2"), True),
    "ci32_le": (np.dtype("<i4"), True),
    "ci32_be": (np.dtype(">i4"), True),
    "cu32_le": (np.dtype("<u4"), True),
    "cu32_be": (np.dtype(">u4"), True),
    "ci8": (np.dtype("i1"), True),
    "cu8": (np.dtype("u1"), True),
    "rf32_le": (np.dtype("<f4"), False),
    "rf32_be": (np.dtype(">f4"), False),
    "rf64_le": (np.dtype("<f8"), False),
    "rf64_be": (np.dtype(">f8"), False),
    "ri16_le": (np.dtype("<i2"), False),
    "ri16_be": (np.dtype(">i2"), False),
    "ru16_le": (np.dtype("<u2"), False),
    "ru16_be": (np.dtype(">u2"), False),
    "ri32_le": (np.dtype("<i4"), False),
    "ri32_be": (np.dtype(">i4"), False),
    "ru32_le": (np.dtype("<u4"), False),
    "ru32_be": (np.dtype(">u4"), False),
    "ri8": (np.dtype("i1"), False),
    "ru8": (np.dtype("u1"), False),
}

_FISSURE_TYPES = {
    "Complex Float 32": (np.dtype("<c8"), False),
    "Complex Float 64": (np.dtype("<c16"), False),
    "Complex Int 16": (np.dtype("<i2"), True),
    "Complex Unsigned Int 16": (np.dtype("<u2"), True),
    "Complex Int 32": (np.dtype("<i4"), True),
    "Complex Unsigned Int 32": (np.dtype("<u4"), True),
    "Complex Int 64": (np.dtype("<i8"), True),
    "Complex Unsigned Int 64": (np.dtype("<u8"), True),
    "Complex Int 8": (np.dtype("i1"), True),
    "Complex Unsigned Int 8": (np.dtype("u1"), True),
    "Float/Float 32": (np.dtype("<f4"), False),
    "Float/Float 64": (np.dtype("<f8"), False),
    "Short/Int 16": (np.dtype("<i2"), False),
    "Unsigned Int 16": (np.dtype("<u2"), False),
    "Int/Int 32": (np.dtype("<i4"), False),
    "Unsigned Int 32": (np.dtype("<u4"), False),
    "Byte/Int 8": (np.dtype("i1"), False),
    "Unsigned Int 8": (np.dtype("u1"), False),
}


def _format_duration(seconds):
    seconds = float(seconds or 0.0)
    if seconds < 1e-3:
        return f"{seconds * 1e6:.3f} us"
    if seconds < 1.0:
        return f"{seconds * 1e3:.3f} ms"
    return f"{seconds:.6g} s"


def _format_frequency(hz):
    hz = float(hz or 0.0)
    if abs(hz) >= 1e6:
        return f"{hz / 1e6:.6f} MHz"
    if abs(hz) >= 1e3:
        return f"{hz / 1e3:.3f} kHz"
    return f"{hz:.3f} Hz"


class OperationMain(Operation):
    """Compute lightweight statistics for one IQ file/range."""

    def __init__(
        self,
        filepath: str = "",
        data_type: str = "Complex Float 32",
        sigmf_datatype: str = "",
        sample_rate_hz: float = 0.0,
        center_frequency_hz: float = 0.0,
        sample_count: int = 0,
        start_sample: int = 0,
        end_sample: int = 0,
        max_samples: int = 1000000,
        node_uid: str = "",
        logger: logging.Logger = logging.getLogger(__name__),
        inspection_callback: Union[Callable, None] = None,
    ) -> None:
        super().__init__(
            node_uid=node_uid,
            logger=logger,
            inspection_callback=inspection_callback,
        )
        self.filepath = str(filepath or "").strip()
        self.data_type = str(data_type or "Complex Float 32").strip()
        self.sigmf_datatype = str(sigmf_datatype or "").strip()
        self.sample_rate_hz = max(0.0, float(sample_rate_hz or 0.0))
        self.center_frequency_hz = float(center_frequency_hz or 0.0)
        self.sample_count = max(0, int(sample_count or 0))
        self.start_sample = max(0, int(start_sample or 0))
        self.end_sample = max(0, int(end_sample or 0))
        self.max_samples = max(1000, min(10000000, int(max_samples or 1000000)))

    def _type_info(self):
        if self.sigmf_datatype in _SIGMF_TYPES:
            return _SIGMF_TYPES[self.sigmf_datatype]
        return _FISSURE_TYPES.get(self.data_type, (np.dtype("<c8"), False))

    def _read_samples(self):
        if not self.filepath or not os.path.isfile(self.filepath):
            raise FileNotFoundError(f"IQ file not found: {self.filepath}")

        dtype, interleaved = self._type_info()
        bytes_per_sample = dtype.itemsize * 2 if interleaved else dtype.itemsize
        available_samples = os.path.getsize(self.filepath) // bytes_per_sample
        total = min(self.sample_count, available_samples) if self.sample_count else available_samples
        start = min(self.start_sample, total)
        end = min(self.end_sample or total, total)
        if end <= start:
            raise ValueError("Inspection selection contains no samples.")

        selection_count = end - start
        step = max(1, int(math.ceil(selection_count / float(self.max_samples))))
        indices = np.arange(start, end, step, dtype=np.int64)

        if interleaved:
            raw = np.memmap(self.filepath, dtype=dtype, mode="r", shape=(total * 2,))
            real = np.asarray(raw[indices * 2], dtype=np.float64)
            imag = np.asarray(raw[indices * 2 + 1], dtype=np.float64)
            if np.issubdtype(dtype, np.integer):
                info = np.iinfo(dtype)
                scale = max(abs(float(info.min)), abs(float(info.max))) or 1.0
                real /= scale
                imag /= scale
            data = real + 1j * imag
        else:
            raw = np.memmap(self.filepath, dtype=dtype, mode="r", shape=(total,))
            data = np.asarray(raw[indices])
            if np.issubdtype(dtype, np.integer):
                info = np.iinfo(dtype)
                scale = max(abs(float(info.min)), abs(float(info.max))) or 1.0
                data = data.astype(np.float64) / scale

        return np.asarray(data), selection_count

    async def _emit_inspection(self, inspection, final=True):
        await self.inspection_callback(
            self.node_uid,
            self.opid,
            inspection,
            final,
        )

    async def run(self) -> None:
        try:
            data, selection_count = self._read_samples()
            if data.size == 0:
                raise ValueError("Inspection analysis read no samples.")

            magnitude = np.abs(data).astype(np.float64)
            power = magnitude ** 2
            epsilon = np.finfo(np.float64).tiny
            values = {
                "Analyzed Samples": int(data.size),
                "Selection Samples": int(selection_count),
                "Mean Magnitude": round(float(np.mean(magnitude)), 6),
                "RMS Magnitude": round(float(np.sqrt(np.mean(power))), 6),
                "Peak Magnitude": round(float(np.max(magnitude)), 6),
                "Average Power": f"{10.0 * math.log10(max(float(np.mean(power)), epsilon)):.3f} dB",
            }

            if self.sample_rate_hz > 0:
                values["Selection Duration"] = _format_duration(
                    selection_count / self.sample_rate_hz
                )

            if self.sample_rate_hz > 0 and np.iscomplexobj(data) and data.size >= 32:
                fft_data = data[: min(data.size, 262144)]
                fft_data = fft_data - np.mean(fft_data)
                spectrum = np.fft.fftshift(
                    np.fft.fft(fft_data * np.hanning(len(fft_data)))
                )
                frequency = np.fft.fftshift(
                    np.fft.fftfreq(len(fft_data), d=1.0 / self.sample_rate_hz)
                )
                peak_index = int(np.argmax(np.abs(spectrum)))
                peak_offset = float(frequency[peak_index])
                values["Peak Spectral Offset"] = _format_frequency(peak_offset)
                if self.center_frequency_hz:
                    values["Peak RF Frequency"] = _format_frequency(
                        self.center_frequency_hz + peak_offset
                    )

            await self._emit_inspection(
                {
                    "title": "Basic IQ Analysis",
                    "values": values,
                },
                final=True,
            )
        except Exception as error:
            try:
                await self._emit_inspection(
                    {
                        "title": "Basic IQ Analysis",
                        "error": str(error),
                        "values": {},
                    },
                    final=True,
                )
            except Exception:
                self.logger.exception("Failed to emit Inspection error result")
            raise