import argparse, json, os, sys
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(".env.agent.secret")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    args = parser.parse_args()

    client = OpenAI(
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_API_BASE"),
    )
    model = os.getenv("LLM_MODEL")

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Answer concisely."},
                {"role": "user", "content": args.question}
            ],
            timeout=55
        )
        answer = resp.choices[0].message.content.strip()
        print(json.dumps({"answer": answer, "tool_calls": []}))
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()