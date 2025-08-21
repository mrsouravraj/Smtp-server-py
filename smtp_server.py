# smtp_server_complete.py
import asyncio
import socket
import re
import os
import uuid
import datetime

MAILBOX_DIR = "mailbox"

# Save email to local mailbox directory as .eml file
def save_email(mail_from, rcpt_to, body):
    os.makedirs(MAILBOX_DIR, exist_ok=True)
    filename = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S") + "_" + str(uuid.uuid4()) + ".eml"
    filepath = os.path.join(MAILBOX_DIR, filename)

    with open(filepath, "w") as f:
        f.write(f"From: {mail_from}\n")
        for rcpt in rcpt_to:
            f.write(f"To: {rcpt}\n")
        f.write("\n")
        f.write(body)

    print(f"📩 Saved email to {filepath}")


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    hostname = socket.gethostname()
    state = {"helo": None, "mail_from": None, "rcpt_to": [], "data": None}

    def send(line: str):
        print(">>", line.strip())
        writer.write((line + "\r\n").encode("ascii"))

    send(f"220 {hostname} SMTP Server ready")
    await writer.drain()

    while True:
        data = await reader.readline()
        if not data:
            break
        message = data.decode("ascii").rstrip("\r\n")
        print("<<", message)

        cmd_upper = message.upper()

        if cmd_upper.startswith("HELO"):
            parts = message.split(maxsplit=1)
            state["helo"] = parts[1] if len(parts) > 1 else None
            send(f"250 {hostname} greets {state['helo']}")

        elif cmd_upper.startswith("MAIL FROM:"):
            if not state["helo"]:
                send("503 Bad sequence of commands")
            else:
                match = re.match(r"MAIL FROM:\s*<([^>]+)>", message, re.IGNORECASE)
                if match:
                    state["mail_from"] = match.group(1)
                    state["rcpt_to"] = []
                    state["data"] = None
                    send("250 OK")
                else:
                    send("501 Syntax error in parameters or arguments")

        elif cmd_upper.startswith("RCPT TO:"):
            if not state["mail_from"]:
                send("503 Bad sequence of commands")
            else:
                match = re.match(r"RCPT TO:\s*<([^>]+)>", message, re.IGNORECASE)
                if match:
                    state["rcpt_to"].append(match.group(1))
                    send("250 OK")
                else:
                    send("501 Syntax error in parameters or arguments")

        elif cmd_upper == "DATA":
            if not state["rcpt_to"]:
                send("503 Bad sequence of commands")
            else:
                send("354 End data with <CRLF>.<CRLF>")
                await writer.drain()

                lines = []
                while True:
                    line = await reader.readline()
                    if not line:
                        break
                    line = line.decode("ascii").rstrip("\r\n")

                    if line == ".":
                        break
                    if line.startswith(".."):  # transparency rule
                        line = line[1:]

                    lines.append(line)

                state["data"] = "\n".join(lines)

                # Save email to mailbox
                save_email(state["mail_from"], state["rcpt_to"], state["data"])

                send("250 OK: Message accepted for delivery")

        elif cmd_upper == "QUIT":
            send("221 Bye")
            break

        else:
            send("502 Command not implemented")

        await writer.drain()

    writer.close()
    await writer.wait_closed()


async def main(host="0.0.0.0", port=2525):
    server = await asyncio.start_server(handle_client, host, port)
    print(f"📡 SMTP server listening on {host}:{port}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
