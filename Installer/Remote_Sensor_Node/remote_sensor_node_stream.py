"""Stream privileged installer output and stop its process group on cancellation."""

import asyncio
import shlex
import sys
from typing import Any

from remote_sensor_node_privilege import PrivilegeContext, PrivilegeError


# SSH signals reach this supervisor. Its child owns a separate process group,
# allowing cancellation to stop apt/make/download children as well as the shell.
SUPERVISOR = """exec </dev/null
child=''
stop() {
    test -n "$child" || return 0
    kill -TERM -- "-$child" 2>/dev/null || true
    sleep 2
    kill -KILL -- "-$child" 2>/dev/null || true
}
trap 'stop; exit 130' HUP INT TERM
setsid "$@" &
child=$!
wait "$child"
"""


async def stream_root_command(
    connection: Any, args: list[str], privilege: PrivilegeContext,
) -> None:
    command = shlex.join(["bash", "-c", SUPERVISOR, "fissure-host-preparation", *args])
    if privilege.mode != "root":
        prefix = "sudo -k -S -p '' -- " if privilege.password else "sudo -n -- "
        command = prefix + command
    process = await connection.create_process(command)
    pumps = []
    try:
        if privilege.password:
            process.stdin.write(privilege.password + "\n")
        process.stdin.write_eof()
        pumps = [asyncio.create_task(_copy_stream(process.stdout, sys.stdout)),
                 asyncio.create_task(_copy_stream(process.stderr, sys.stderr))]
        await asyncio.gather(*pumps)
        await process.wait_closed()
        if process.exit_status != 0:
            raise PrivilegeError(f"Host preparation failed (exit {process.exit_status}); see output above")
    finally:
        if process.exit_status is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait_closed(), timeout=10)
            except asyncio.TimeoutError:
                process.kill()
                process.close()
        for task in pumps:
            task.cancel()
        if pumps:
            await asyncio.gather(*pumps, return_exceptions=True)


async def _copy_stream(reader: Any, output: Any) -> None:
    # Read chunks instead of lines: build tools can emit extremely long lines.
    while chunk := await reader.read(4096):
        output.write(chunk)
        output.flush()
