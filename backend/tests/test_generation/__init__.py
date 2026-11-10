"""
Unit tests for the generation pipeline.

Planned test cases:

  test_generator.py
    - generate_answer() calls OllamaClient.chat() with the correct model.
    - The prompt contains the user question.
    - The prompt contains the assembled context.
    - The system prompt is present in the messages.
    - Temperature is forwarded to the chat call.
    - Sources in GenerationResult match the input chunks.
    - Ollama connection failure raises OllamaConnectionError.
    - Empty chunk list produces an answer that acknowledges missing context.
    - _build_prompt() assigns [Source N] labels matching the chunk order.
"""
