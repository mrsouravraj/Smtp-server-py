import asyncio
import pathlib
import hashlib
from typing import List, Dict, Tuple

# ===== Configuration =====
MAILBOX_DIR = pathlib.Path("mailbox")  # Uses the same folder your SMTP server writes to
POP3_HOST = "0.0.0.0"
POP3_PORT = 1100                        # Use 1100 for dev; 110 is privileged
USERNAME = "user"
PASSWORD = "pass"
# =========================

CRLF = "\r\n"

class Maildrop:
    """
    Represents one POP3 maildrop for a user.
    Loads .eml files from MAILBOX_DIR and exposes POP3 views (STAT/LIST/RETR/DELE).
    """
    def __init__(self, root: pathlib.Path):
        self.root = root
        self.messages: List[pathlib.Path] = []
        self.sizes: List[int] = []
        self.uidls: List[str] = []
        self.deleted: Dict[int, bool] = {}  # 1-based index -> deleted?

    def refresh(self):
        self.messages = sorted([p for p in self.root.glob("*.eml") if p.is_file()])
        self.sizes = [p.stat().st_size for p in self.messages]
        self.uidls = [self._uidl_for(p) for p in self.messages]
        self.deleted = {}

    def count_and_octets(self) -> Tuple[int, int]:
        count = sum(0 if self.deleted.get(i+1) else 1 for i in range(len(self.messages)))
        octets = sum(self.sizes[i] for i in range(len(self.messages)) if not self.deleted.get(i+1))
        return count, octets

    def list_all(self) -> List[Tuple[int, int]]:
        return [(i+1, self.sizes[i]) for i in range(len(self.messages)) if not self.deleted.get(i+1)]

    def list_one(self, idx: int) -> Tuple[int, int]:
        self._ensure_index(idx)
        if self.deleted.get(idx):
            raise IndexError("Message already deleted")
        return idx, self.sizes[idx-1]

    def retr(self, idx: int) -> bytes:
        self._ensure_index(idx)
        if self.deleted.get(idx):
            raise IndexError("Message already deleted")
        with self.messages[idx-1].open("rb") as f:
            data = f.read()
        # Normalize to CRLF lines and dot-stuff as per POP3 transmission rules
        text = data.decode("utf-8", errors="replace")
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        out_lines = []
        for line in lines:
            if line.startswith("."):
                out_lines.append("." + line)  # dot-stuffing
            else:
                out_lines.append(line)
        payload = (CRLF.join(out_lines) + CRLF + "." + CRLF).encode("utf-8", errors="replace")
        return payload

    def dele(self, idx: int):
        self._ensure_index(idx)
        if self.deleted.get(idx):
            raise IndexError("Message already deleted")
        self.deleted[idx] = True

    def rset(self):
        self.deleted = {}

    def commit(self):
        # Physically remove deleted files
        for i, p in enumerate(self.messages, start=1):
            if self.deleted.get(i):
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass
        # Reload state after deletion to keep things consistent
        self.refresh()

    def _ensure_index(self, idx: int):
        if idx < 1 or idx > len(self.messages):
            raise IndexError("No such message")

    @staticmethod
    def _uidl_for(path: pathlib.Path) -> str:
        # Simple UIDL from filename + size hash
        h = hashlib.sha1()
        h.update(path.name.encode("utf-8"))
        try:
            h.update(str(path.stat().st_size).encode("ascii"))
            h.update(str(int(path.stat().st_mtime)).encode("ascii"))
        except Exception:
            pass
        return h.hexdigest()


class POP3Session:
    """
    A minimal POP3 state machine (AUTH -> TRANSACTION -> UPDATE).
    """
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.r = reader
        self.w = writer
        self.state = "AUTH"  # AUTH or TRANSACTION
        self.user = None
        self.maildrop = Maildrop(MAILBOX_DIR)

    async def run(self):
        await self._send_ok("POP3 server ready")
        while True:
            line = await self.r.readline()
            if not line:
                break
            raw = line.decode("utf-8", errors="replace").rstrip("\r\n")
            cmd, *args = raw.split()
            cmd_u = cmd.upper()

            try:
                if self.state == "AUTH":
                    if cmd_u == "USER":
                        await self._cmd_user(args)
                    elif cmd_u == "PASS":
                        await self._cmd_pass(args)
                    elif cmd_u == "QUIT":
                        await self._send_ok("Bye")
                        break
                    else:
                        await self._send_err("Authenticate first (USER/PASS)")
                elif self.state == "TRANSACTION":
                    if cmd_u == "STAT":
                        await self._cmd_stat()
                    elif cmd_u == "LIST":
                        await self._cmd_list(args)
                    elif cmd_u == "RETR":
                        await self._cmd_retr(args)
                    elif cmd_u == "DELE":
                        await self._cmd_dele(args)
                    elif cmd_u == "NOOP":
                        await self._send_ok()
                    elif cmd_u == "RSET":
                        self.maildrop.rset()
                        await self._send_ok("Reset")
                    elif cmd_u == "QUIT":
                        # Enter UPDATE state: commit deletions, then close
                        self.maildrop.commit()
                        await self._send_ok("Bye")
                        break
                    else:
                        await self._send_err("Unknown or unsupported command")
                else:
                    await self._send_err("Bad state")
            except Exception as e:
                await self._send_err(str(e))

        try:
            self.w.close()
            await self.w.wait_closed()
        except Exception:
            pass

    # ===== AUTH commands =====
    async def _cmd_user(self, args: List[str]):
        if len(args) != 1:
            await self._send_err("Syntax: USER <name>")
            return
        self.user = args[0]
        await self._send_ok("User accepted, send PASS")

    async def _cmd_pass(self, args: List[str]):
        if self.user is None:
            await self._send_err("Send USER first")
            return
        if len(args) != 1:
            await self._send_err("Syntax: PASS <password>")
            return
        pw = args[0]
        if self.user == USERNAME and pw == PASSWORD:
            if not MAILBOX_DIR.exists():
                MAILBOX_DIR.mkdir(parents=True, exist_ok=True)
            self.maildrop.refresh()
            self.state = "TRANSACTION"
            count, octets = self.maildrop.count_and_octets()
            await self._send_ok(f"Mailbox locked and ready, {count} messages ({octets} octets)")
        else:
            await self._send_err("Authentication failed")

    # ===== TRANSACTION commands =====
    async def _cmd_stat(self):
        count, octets = self.maildrop.count_and_octets()
        await self._send_ok(f"{count} {octets}")

    async def _cmd_list(self, args: List[str]):
        if len(args) == 0:
            all_msgs = self.maildrop.list_all()
            await self._send_ok(f"{len(all_msgs)} messages")
            for i, size in all_msgs:
                await self._write_line(f"{i} {size}")
            await self._write_line(".")
        elif len(args) == 1:
            try:
                idx = int(args[0])
            except ValueError:
                await self._send_err("Syntax: LIST [msg]")
                return
            i, size = self.maildrop.list_one(idx)
            await self._send_ok(f"{i} {size}")
        else:
            await self._send_err("Syntax: LIST [msg]")

    async def _cmd_retr(self, args: List[str]):
        if len(args) != 1:
            await self._send_err("Syntax: RETR <msg>")
            return
        try:
            idx = int(args[0])
        except ValueError:
            await self._send_err("Syntax: RETR <msg>")
            return
        payload = self.maildrop.retr(idx)
        # +OK <octets> (octets = size of message on disk; fine to reuse)
        _, size = self.maildrop.list_one(idx)
        await self._send_ok(f"{size} octets")
        self.w.write(payload)
        await self.w.drain()

    async def _cmd_dele(self, args: List[str]):
        if len(args) != 1:
            await self._send_err("Syntax: DELE <msg>")
            return
        try:
            idx = int(args[0])
        except ValueError:
            await self._send_err("Syntax: DELE <msg>")
            return
        self.maildrop.dele(idx)
        await self._send_ok(f"Message {idx} deleted")

    # ===== IO helpers =====
    async def _send_ok(self, msg: str = "OK"):
        await self._write_line(f"+OK {msg}")

    async def _send_err(self, msg: str = "Error"):
        await self._write_line(f"-ERR {msg}")

    async def _write_line(self, s: str):
        data = (s + CRLF).encode("utf-8", errors="replace")
        self.w.write(data)
        await self.w.drain()


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    session = POP3Session(reader, writer)
    await session.run()


async def main(host=POP3_HOST, port=POP3_PORT):
    server = await asyncio.start_server(handle_client, host, port)
    addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
    print(f"📮 POP3 server listening on {addrs}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 POP3 server stopped")
