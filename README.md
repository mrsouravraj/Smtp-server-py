# Minimal Python Mail Server

This project contains a **minimal SMTP and POP3 server** written in Python using `asyncio`.

It allows you to:

* Receive emails via SMTP
* Store emails locally as `.eml` files
* Access emails using a basic POP3 server
* Support multiple concurrent clients

---

## Features

### SMTP Server

* Handles:

  * `HELO` handshake
  * `MAIL FROM:<sender>`
  * `RCPT TO:<recipient>` (multiple recipients supported)
  * `DATA` (email headers + body)
  * `QUIT`
* Supports **dot-stuffing / transparency** for message bodies
* Stores received emails in `mailbox/` directory as `.eml` files
* Handles **concurrent clients** using `asyncio`

### POP3 Server

* Simple POP3 server serving the `.eml` files from `mailbox/`
* Supports:

  * `USER` / `PASS` authentication (single default user)
  * `STAT` – show mailbox stats
  * `LIST [msg]` – list messages
  * `RETR <msg>` – retrieve full message
  * `DELE <msg>` – mark message for deletion
  * `RSET` – unmark deleted messages
  * `NOOP` – no-op
  * `QUIT` – exit and commit deletions
* Handles multiple concurrent clients
* Dot-stuffing handled when sending messages

---

## Prerequisites

* Python 3.8+
* Works on Linux, macOS, Windows
* No external dependencies

---

## Setup

1. Clone or download this repository.
2. Ensure the directory structure:

```
project/
├── smtp_server.py
├── pop3_server.py
└── mailbox/           # Emails will be stored here
```

> `mailbox/` will be created automatically if it doesn’t exist.

---

## SMTP Server Usage

1. Run the SMTP server:

```bash
python smtp_server_complete.py
```

2. Connect using `telnet`, `nc`, or an email client configured to `localhost`:

```bash
telnet localhost 2525
```

3. Example SMTP session:

```
220 myhost SMTP Server ready
HELO client.example.com
250 myhost greets client.example.com
MAIL FROM:<alice@example.com>
250 OK
RCPT TO:<bob@example.com>
250 OK
DATA
354 End data with <CRLF>.<CRLF>
Subject: Test Email
Hello Bob,
This is a test.
.
250 OK: Message accepted for delivery
QUIT
221 Bye
```

4. Emails will be saved as `.eml` files in `mailbox/`.

---

## POP3 Server Usage

1. Run the POP3 server:

```bash
python pop3_server.py
```

2. Connect using `telnet`:

```bash
telnet 127.0.0.1 1100
```

3. Example POP3 session:

```
+OK POP3 server ready
USER user
+OK User accepted, send PASS
PASS pass
+OK Mailbox locked and ready, 1 messages (1234 octets)
STAT
+OK 1 1234
LIST
+OK 1 messages
1 1234
.
RETR 1
+OK 1234 octets
<email content>
.
DELE 1
+OK Message 1 deleted
QUIT
+OK Bye
```

> **Default credentials**: `user` / `pass`

---

## Notes

* SMTP server listens on port **2525** (non-privileged). Change to **25** if running as root.
* POP3 server listens on port **1100** (non-privileged). Change to **110** for production.
* Supports multiple clients concurrently using `asyncio`.
* Emails are stored locally and can be accessed or deleted via POP3.

---

## License

MIT License
