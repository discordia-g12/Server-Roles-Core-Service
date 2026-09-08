from fastapi import FastAPI

app = FastAPI(title="Server Roles Core Service")

@app.get("/")
def read_root():
    return {"message": "Welcome to Server Roles Core Service API"}

