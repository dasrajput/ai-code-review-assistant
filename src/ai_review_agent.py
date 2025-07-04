import os
import json
import logging
import requests
import re
from together import Together
from config import API_KEY

# Set up logging for debug statements
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CodeReviewAgent:
    def __init__(self):
        if not API_KEY:
            logger.error("API_KEY not set in config.py")
            raise ValueError("API_KEY not set in config.py")
        
        self.client = Together(api_key=API_KEY)
        self.log_file_path = os.path.join('src', 'logs', 'pr_logs.json')
        self.file_entries = self._load_logs()
        logger.info(f"Successfully loaded {self.log_file_path}")

    def _load_logs(self):
        try:
            with open(self.log_file_path, 'r') as f:
                logs = json.load(f)
                return logs[0]["output"]
        except (FileNotFoundError, json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error(f"Error reading {self.log_file_path}: {e}")
            raise

    def fetch_file_content(self, raw_url):
        try:
            logger.info(f"Fetching content from {raw_url}")
            response = requests.get(raw_url, timeout=10)
            response.raise_for_status()
            logger.info(f"Successfully fetched content from {raw_url}")
            return response.text
        except requests.RequestException as e:
            logger.error(f"Error fetching {raw_url}: {e}")
            return None

    def detect_language(self, filename, content):
        extensions = {
            '.cpp': 'cpp',
            '.h': 'cpp',
            '.py': 'python',
            '.java': 'java',
            '.js': 'javascript'
        }
        ext = os.path.splitext(filename)[1].lower()
        
        if ext in extensions:
            return extensions[ext]
        
        if 'def' in content or 'import' in content:
            return 'python'
        elif 'public class' in content:
            return 'java'
        elif 'function' in content or 'let' in content:
            return 'javascript'
        return 'cpp'

    def _get_cached_review(self, filename, raw_url):
        cache_dir = os.path.join('src', 'cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, f"{os.path.basename(filename)}.json")
        if os.path.exists(cache_file):
            with open(cache_file, 'r') as f:
                return json.load(f).get("review")
        return None

    def _cache_review(self, filename, review):
        cache_dir = os.path.join('src', 'cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, f"{os.path.basename(filename)}.json")
        with open(cache_file, 'w') as f:
            json.dump({"review": review}, f)

    def generate_prompt(self, filename, content):
        language = self.detect_language(filename, content)
        prompt_templates = {
            'cpp': """You are a world-class C++ code reviewer with extensive experience in modern C++ standards. Your task is to review the code from '{filename}':\n{content}\nDeliver a PERFECT, concise response consisting EXCLUSIVELY of 4-6 bullet points, each an actionable suggestion with at least one specific code example. Cover ONLY these unique categories: code quality (readability, structure), potential bugs, modern C++ best practices (e.g., const correctness, C++20 features), performance optimizations, and general improvements. DO NOT include internal reasoning, <think> tags, step-by-step analysis, repeat categories, or any text outside bullet points. Failure to comply will render the review unusable—MUST adhere strictly. Use this example format:\n- **Potential Bugs**: Fix overcounting in UTF-8 length; e.g., `if (is_high_surrogate()) length += 4; else length += 3;`\nKeep responses under 300 words, assuming a low temperature (e.g., 0.4) for precision.""",
            'python': """You are a world-class Python code reviewer with extensive experience in PEP 8 and Python best practices. Your task is to review the code from '{filename}':\n{content}\nDeliver a PERFECT, concise response consisting EXCLUSIVELY of 4-6 bullet points, each an actionable suggestion with at least one specific code example. Cover ONLY these unique categories: code quality (PEP 8, structure), potential bugs, Python best practices (e.g., type hints, context managers), performance optimizations, and general improvements. DO NOT include internal reasoning, <think> tags, step-by-step analysis, repeat categories, or any text outside bullet points. Failure to comply will render the review unusable—MUST adhere strictly. Use this example format:\n- **Potential Bugs**: Handle None cases; e.g., `if value is not None: return value`\nKeep responses under 300 words, assuming a low temperature (e.g., 0.4) for precision.""",
            'java': """You are a world-class Java code reviewer with extensive experience in Java best practices. Your task is to review the code from '{filename}':\n{content}\nDeliver a PERFECT, concise response consisting EXCLUSIVELY of 4-6 bullet points, each an actionable suggestion with at least one specific code example. Cover ONLY these unique categories: code quality (structure, naming), potential bugs, Java best practices (e.g., exception handling, interfaces), performance optimizations, and general improvements. DO NOT include internal reasoning, <think> tags, step-by-step analysis, repeat categories, or any text outside bullet points. Failure to comply will render the review unusable—MUST adhere strictly. Use this example format:\n- **Potential Bugs**: Add null checks; e.g., `if (object != null) { process(object); }`\nKeep responses under 300 words, assuming a low temperature (e.g., 0.4) for precision.""",
            'javascript': """You are a world-class JavaScript code reviewer with extensive experience in ES6+ and modern JS practices. Your task is to review the code from '{filename}':\n{content}\nDeliver a PERFECT, concise response consisting EXCLUSIVELY of 4-6 bullet points, each an actionable suggestion with at least one specific code example. Cover ONLY these unique categories: code quality (structure, ES6+), potential bugs, JavaScript best practices (e.g., async/await, modules), performance optimizations, and general improvements. DO NOT include internal reasoning, <think> tags, step-by-step analysis, repeat categories, or any text outside bullet points. Failure to comply will render the review unusable—MUST adhere strictly. Use this example format:\n- **Potential Bugs**: Prevent race conditions with async; e.g., `await lock.acquire();`\nKeep responses under 300 words, assuming a low temperature (e.g., 0.4) for precision."""
        }
        template = prompt_templates.get(language, prompt_templates['cpp'])
        return template.format(filename=filename, content=content)

    def filter_think_tags(self, review):
        return re.sub(r'<think>.*?</think>', '', review, flags=re.DOTALL).strip()

    def review_files(self):
        reviews = []
        for entry in self.file_entries:
            filename = entry.get("file")
            raw_url = entry.get("raw_url")

            if not filename or not raw_url:
                logger.warning(f"Invalid entry, missing 'file' or 'raw_url': {entry}")
                continue

            content = self.fetch_file_content(raw_url)
            if content is None:
                logger.warning(f"Skipping review for {filename} due to fetch failure")
                continue

            cached_review = self._get_cached_review(filename, raw_url)
            if cached_review:
                review = cached_review
            else:
                try:
                    review = self._get_review(filename, content)
                    if review:
                        self._cache_review(filename, review)
                except Exception as e:
                    logger.error(f"Failed to get review for {filename}: {e}")
                    continue

            if review:
                filtered_review = self.filter_think_tags(review)
                reviews.append({"file": filename, "review": filtered_review})

        return reviews

    def _get_review(self, filename, content):
        prompt = self.generate_prompt(filename, content)
        logger.info(f"Prepared prompt for {filename} (detected language: {self.detect_language(filename, content)})")

        try:
            logger.info(f"Sending request to Together AI for {filename}")
            response = self.client.chat.completions.create(
                model="deepseek-ai/DeepSeek-R1-Distill-Llama-70B-free",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=4096,
                stream=False
            )
            logger.info(f"Received review for {filename}")
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error getting review from API: {e}")
            return None

def main():
    try:
        agent = CodeReviewAgent()
        reviews = agent.review_files()
        
        if reviews:
            logger.info("Printing all reviews")
            for review in reviews:
                print(f"\n=== Review for {review['file']} ===\n{review['review']}\n")
        else:
            logger.warning("No reviews generated")
            
    except Exception as e:
        logger.error(f"Script execution failed: {e}")
        return 1
    
    logger.info("Script execution completed successfully")
    return 0

if __name__ == "__main__":
    exit(main())