import logging
from fastapi import FastAPI, File, HTTPException
from extractor import SuryaWorkerExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ocr-worker.main")

app = FastAPI(
    title="Surya OCR & Layout Worker",
    description="Microservice providing isolated Surya OCR and Layout extraction on CPU",
    version="1.0.0",
)

extractor = SuryaWorkerExtractor(device="cpu")


@app.get("/health")
def health():
    """Health check endpoint — responds immediately without waiting for inference."""
    return {
        "status": "ok" if extractor.available else "degraded",
        "device": extractor.device,
        "available": extractor.available,
    }


@app.post("/process")
def process_image(file: bytes = File(...)):
    """Synchronous endpoint executed in worker threadpool to prevent blocking the async event loop."""
    if not file:
        raise HTTPException(status_code=400, detail="Empty file payload")

    result = extractor.process(file)
    return result
