import asyncio
from dotenv import load_dotenv
load_dotenv()

from backend.app.providers.model_provider import create_providers
from backend.app.scheduler.engine import run_benchmark

async def main():
    providers = create_providers()
    model_ids = list(providers.keys())
    
    print(f"Running 03-interpreter with: {model_ids}")
    
    round_id = await run_benchmark(
        problem_ids=["03-interpreter"],
        model_uuids=model_ids,
        providers=providers,
        round_name="03-interpreter 全模型评测"
    )
    print(f"Round ID: {round_id}")

asyncio.run(main())
