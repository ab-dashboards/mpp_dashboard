"""Start an ngrok tunnel for a local Streamlit app."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pyngrok import conf, ngrok


def main() -> None:
    load_dotenv()

    ngrok_path = os.getenv("NGROK_PATH")
    auth_token = os.getenv("NGROK_AUTH_TOKEN")
    port = int(os.getenv("NGROK_PORT", "8501"))

    if ngrok_path:
        conf.get_default().ngrok_path = ngrok_path

    if not auth_token:
        raise SystemExit("NGROK_AUTH_TOKEN is required in environment.")

    ngrok.set_auth_token(auth_token)
    public_url = ngrok.connect(port, "http")
    print(f"🚀 ngrok tunnel established: {public_url}")
    input("Press ENTER to close the tunnel and exit\n")


if __name__ == "__main__":
    main()
