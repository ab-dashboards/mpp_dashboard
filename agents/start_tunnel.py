# File: start_tunnel.py
from pyngrok import ngrok, conf

# ← point this to the EXE you just placed
conf.get_default().ngrok_path = (
    r"C:\Users\Lenovo\PycharmProjects\PythonProjectIEG\mpp_dashboard\ngrok\ngrok.exe"
)

# only need to set this once; your token
ngrok.set_auth_token("2yZTffNu2JANggDEAZ5jWk5fNo2_7Ch33WLdFdUQuH49MYabF")

public_url = ngrok.connect(8501, "http")
print(f"🚀 ngrok tunnel established: {public_url}")

input("Press ENTER to close the tunnel and exit\n")
