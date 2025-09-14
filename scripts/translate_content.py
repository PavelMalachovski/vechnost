#!/usr/bin/env python3
"""Translation script for Vechnost content files."""

import os
import sys
import yaml
import time
from pathlib import Path
from typing import Dict, Any, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from deep_translator import GoogleTranslator
    HAS_GOOGLE_TRANSLATOR = True
except ImportError:
    HAS_GOOGLE_TRANSLATOR = False

try:
    import deepl
    HAS_DEEPL = True
except ImportError:
    HAS_DEEPL = False


def translate_text(text: str, target_lang: str, source_lang: str = "ru") -> str:
    """Translate text using available translation service."""
    if not text or not text.strip():
        return text

    # Try DeepL first if available and API key is set
    if HAS_DEEPL and os.getenv("DEEPL_API_KEY"):
        try:
            translator = deepl.Translator(os.getenv("DEEPL_API_KEY"))
            result = translator.translate_text(text, target_lang=target_lang, source_lang=source_lang)
            return result.text
        except Exception as e:
            print(f"DeepL translation failed: {e}")

    # Fallback to Google Translate
    if HAS_GOOGLE_TRANSLATOR:
        try:
            # Map language codes
            lang_map = {
                "en": "en",
                "cs": "cs"
            }
            target = lang_map.get(target_lang, target_lang)

            translator = GoogleTranslator(source=source_lang, target=target)
            result = translator.translate(text)
            time.sleep(0.1)  # Rate limiting
            return result
        except Exception as e:
            print(f"Google translation failed: {e}")

    # Manual fallback
    return f"[TODO: Translate to {target_lang}] {text}"


def translate_content(data: Dict[str, Any], target_lang: str) -> Dict[str, Any]:
    """Recursively translate content structure."""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            result[key] = translate_content(value, target_lang)
        return result
    elif isinstance(data, list):
        result = []
        for item in data:
            result.append(translate_content(item, target_lang))
        return result
    elif isinstance(data, str):
        return translate_text(data, target_lang)
    else:
        return data


def main():
    """Main translation function."""
    if not HAS_GOOGLE_TRANSLATOR and not (HAS_DEEPL and os.getenv("DEEPL_API_KEY")):
        print("Error: No translation service available.")
        print("Install deep-translator: pip install deep-translator")
        print("Or set DEEPL_API_KEY environment variable for DeepL")
        return 1

    # Load Russian content
    ru_path = Path(__file__).parent.parent / "content" / "ru.yml"
    if not ru_path.exists():
        print(f"Error: Russian content file not found: {ru_path}")
        return 1

    with open(ru_path, 'r', encoding='utf-8') as f:
        ru_content = yaml.safe_load(f)

    # Translate to English and Czech
    for target_lang in ["en", "cs"]:
        print(f"Translating to {target_lang}...")

        # Translate content
        translated = translate_content(ru_content, target_lang)

        # Save translated content
        output_path = Path(__file__).parent.parent / "content" / f"{target_lang}.yml"
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(translated, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        print(f"Saved {target_lang} translation to {output_path}")

    print("Translation complete!")
    print("Please review the translated files and update any TODO markers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
