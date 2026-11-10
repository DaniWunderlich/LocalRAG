# Local RAG – Produktvision

## 1. Vision

Wir entwickeln ein schlankes, vollständig lokal betriebenes **Retrieval-Augmented-Generation-System (RAG)**, mit dem sich eigene Dokumente und Wissensbestände mithilfe lokaler LLMs durchsuchen und befragen lassen.

Das System soll einfach zu installieren, verständlich aufgebaut und langfristig erweiterbar sein.

**Leitgedanke:** So einfach wie möglich, so komplex wie nötig.

## 2. Produktziele

* **100 % lokal:** Dokumente, Embeddings und Anfragen bleiben innerhalb der eigenen Infrastruktur. Keine Abhängigkeit von Cloud- oder KI-Diensten.
* **Einfacher Betrieb:** Mit wenigen Containern starten und ohne aufwendige Konfiguration nutzen.
* **Eigenes Wissen nutzen:** Dokumente hochladen, indexieren, durchsuchen und in natürlicher Sprache befragen.
* **Nachvollziehbare Antworten:** Antworten enthalten überprüfbare Quellenangaben. Die verwendeten Textstellen können eingesehen werden.
* **Modularer Aufbau:** Komponenten lassen sich unabhängig weiterentwickeln oder austauschen.
* **Plattformunabhängigkeit:** Zunächst Docker Compose, später Kubernetes beziehungsweise k3s, ohne grundlegende Architekturänderungen.
* **Kontrollierbarkeit:** Indexierung, Suche und Antwortgenerierung bleiben transparent und überprüfbar.

## 3. Benutzererlebnis

Der Nutzer öffnet die Anwendung im Browser und kann:

1. Eigene Dokumente hochladen und verwalten.
2. Fragen zu seinen Dokumenten in natürlicher Sprache stellen.
3. Antworten mit konkreten Quellenangaben erhalten.
4. Die gefundenen Textstellen und verwendeten Quellen einsehen.
5. Das lokale LLM für die Antwortgenerierung auswählen.

Die Bedienung bleibt bewusst übersichtlich und erfordert keine Kenntnisse über RAG, Vektordatenbanken oder LLM-Technologien.

## 4. Technische Leitplanken

Wir setzen auf wenige, klar getrennte Komponenten:

| Bereich             | Festlegung                |
| ------------------- | ------------------------- |
| Benutzeroberfläche  | Streamlit                 |
| Anwendungsbackend   | FastAPI                   |
| Vektordatenbank     | Qdrant                    |
| Lokale KI           | Bestehende Ollama-Instanz |
| Initialer Betrieb   | Docker Compose            |
| Zukünftiger Betrieb | k3s / Kubernetes          |

Weitere technische Entscheidungen werden in der `SPEC.md` dokumentiert.

## 5. Bewusste Abgrenzung

Die erste Version ist **kein universelles KI-Framework und keine Agentenplattform**.

Wir verzichten zunächst auf komplexe Workflows, Knowledge Graphs, Cloud-Integrationen, umfangreiche Benutzerverwaltung und zusätzliche Infrastruktur.

Neue Funktionen werden ergänzt, wenn ein konkreter Bedarf besteht.

## 6. Erfolgskriterium

Die erste Version ist erfolgreich, wenn ein Nutzer die Anwendung lokal starten, eigene Dokumente hochladen und anschliessend zuverlässige, nachvollziehbare Antworten auf Fragen zu diesen Dokumenten erhalten kann.

**Das Ergebnis ist ein kleines, eigenständiges RAG-System, das einfach funktioniert, verständlich bleibt und mit zukünftigen Anforderungen wachsen kann.**

