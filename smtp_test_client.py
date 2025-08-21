import socket
import time

def smtp_client(host="127.0.0.1", port=2525, delay=1):
    with socket.create_connection((host, port)) as sock:
        f = sock.makefile("rw")

        print(f.readline().strip())  # 220 greeting

        f.write("HELO client.test\r\n")
        f.flush()
        print(f.readline().strip())

        f.write("MAIL FROM:<alice@example.com>\r\n")
        f.flush()
        print(f.readline().strip())

        f.write("RCPT TO:<bob@example.com>\r\n")
        f.flush()
        print(f.readline().strip())

        f.write("DATA\r\n")
        f.flush()
        print(f.readline().strip())

        # Send the body slowly
        for line in ["Subject: Slow Test", "Hello,", "This is a slow email.", "Bye."]:
            f.write(line + "\r\n")
            f.flush()
            time.sleep(delay)

        # End of DATA
        f.write(".\r\n")
        f.flush()
        print(f.readline().strip())

        f.write("QUIT\r\n")
        f.flush()
        print(f.readline().strip())

if __name__ == "__main__":
    smtp_client(delay=2)  # slower for concurrency testing
