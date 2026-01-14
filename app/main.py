from fastapi import FastAPI

app = FastAPI(title="GP Triage Bot API")

@app.get("/hello")
def hello():
    return {"message": "Hello! Your API is running."}
