"""
Quick diagnostic: probe a miner's CGMiner port 4028 and show raw response.
Usage: python debug_avalon.py <ip>
"""
import asyncio
import json
import sys


async def probe(ip: str):
    print(f"\n=== Probing {ip}:4028 ===")
    for cmd_name, cmd in [
        ("version", b'{"command":"version"}'),
        ("stats",   b'{"command":"stats"}'),
    ]:
        print(f"\n--- Command: {cmd_name} ---")
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, 4028), timeout=5.0
            )
            writer.write(cmd)
            await writer.drain()
            data = b""
            try:
                while True:
                    chunk = await asyncio.wait_for(reader.read(8192), timeout=3.0)
                    if not chunk:
                        break
                    data += chunk
                    if b"\x00" in chunk:
                        break
            except asyncio.TimeoutError:
                pass
            writer.close()
            if data:
                text = data.decode("utf-8", errors="ignore").rstrip("\x00").strip()
                try:
                    parsed = json.loads(text)
                    print(json.dumps(parsed, indent=2)[:2000])
                    if cmd_name == "version" and "VERSION" in parsed:
                        v = parsed["VERSION"][0] if parsed["VERSION"] else {}
                        print(f"\n  >> Type       : {v.get('Type', '(empty)')!r}")
                        print(f"  >> CGMiner    : {v.get('CGMiner', '(empty)')!r}")
                        print(f"  >> Miner      : {v.get('Miner', '(empty)')!r}")
                        print(f"  >> Description: {v.get('Description', '(empty)')!r}")
                        print(f"  >> CompileTime: {v.get('CompileTime', '(empty)')!r}")
                except json.JSONDecodeError:
                    print(f"  Raw (not JSON): {text[:500]}")
            else:
                print("  No data received")
        except Exception as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_avalon.py <ip> [ip2] [ip3] ...")
        sys.exit(1)
    for ip in sys.argv[1:]:
        asyncio.run(probe(ip))
