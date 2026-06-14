"""Schneller manueller Test des Agenten-Kerns -- ohne GUI, ohne Tauri.

Voraussetzung: Ollama laeuft und das Modell ist geladen
(z.B. `ollama pull qwen2.5:7b`).

Aufruf:  python test_agent.py
"""
from agent import local_llm, router


def main() -> None:
    print("Lokale KI erreichbar:", local_llm.is_available())

    messages = [{"role": "user", "content": "Erklaere in zwei Saetzen, was DSGVO bedeutet."}]
    result = router.handle_task(messages)

    print("\n--- Ergebnis ---")
    print("Typ:    ", result["type"])
    if result["type"] == "answer":
        print("Quelle: ", result["source"], "| Konfidenz:", result.get("confidence"))
        print("Text:   ", result["text"])
    elif result["type"] == "consent_required":
        print("Grund:  ", result["reason"])
        print("Daten:  ", result["data_preview"])
        print("(In der echten App erscheint jetzt der Einwilligungs-Dialog.)")


if __name__ == "__main__":
    main()
