# Local RAG – Technical Specification

**Version:** 0.1
**Status:** Initial Specification
**Deployment:** Docker Compose → Kubernetes / k3s

---

## 1. Projektübersicht

Local RAG ist eine schlanke, vollständig lokal betriebene Anwendung zur wissensbasierten Interaktion mit eigenen Dokumenten.

Das System nutzt Retrieval-Augmented Generation (RAG), um relevante Informationen aus indexierten Dokumenten zu finden und einem lokalen Large Language Model als Kontext bereitzustellen.

Die Anwendung besteht aus wenigen, unabhängig betreibbaren Komponenten.

### Architekturprinzipien

1. **Local First:** Keine externen KI- oder Cloud-Dienste erforderlich.
2. **Keep It Simple:** Möglichst wenige Komponenten und Abhängigkeiten.
3. **Modularität:** Klare Trennung von Ingestion, Retrieval und Generation.
4. **Austauschbarkeit:** Komponenten kommunizieren über definierte Schnittstellen.
5. **Portabilität:** Keine Docker-Compose-spezifische Anwendungslogik.
6. **Transparenz:** Suchergebnisse und verwendete Quellen sind nachvollziehbar.
7. **Keine Überarchitektur:** Komplexität wird erst bei konkretem Bedarf eingeführt.

---

# 2. Technologie-Stack

## 2.1 Komponenten

| Bereich                   | Technologie        | Verantwortung                       |
| ------------------------- | ------------------ | ----------------------------------- |
| Frontend                  | Python / Streamlit | Browser-Oberfläche                  |
| Backend                   | Python / FastAPI   | REST API und RAG-Orchestrierung     |
| Vector Database           | Qdrant             | Vektoren, Text-Chunks und Metadaten |
| LLM Runtime               | Ollama             | Embeddings und Textgenerierung      |
| Dokumentenparser          | pypdf, python-docx | Textextraktion                      |
| Chunking                  | Python             | Strukturierte Textaufteilung        |
| HTTP Client               | httpx              | Kommunikation mit Ollama            |
| Vector Client             | qdrant-client      | Kommunikation mit Qdrant            |
| Konfiguration             | Umgebungsvariablen | Laufzeitkonfiguration               |
| Container                 | Docker             | Komponentenisolierung               |
| Orchestrierung            | Docker Compose     | Initiales Deployment                |
| Zukünftige Orchestrierung | Kubernetes / k3s   | Alternatives Deployment             |

### Versionsmanagement

Zum Projektstart werden die eingesetzten stabilen Versionen geprüft und festgelegt.

Dabei gelten folgende Regeln:

* Python-Version explizit festlegen.
* Python-Abhängigkeiten über `uv` verwalten und mittels Lockfile fixieren.
* Docker-Images mit expliziten Versionen referenzieren.
* Keine Verwendung von `latest` in reproduzierbaren Deployments.
* Eingesetzte Versionen in der Projektdokumentation festhalten.

## 2.2 Bewusste Technologieentscheidungen

Folgende Komponenten werden zunächst nicht verwendet:

* LangChain
* LlamaIndex
* PostgreSQL
* Redis
* RabbitMQ
* Elasticsearch
* Neo4j
* Kubernetes-spezifische Operatoren

Die notwendige RAG-Orchestrierung wird direkt in Python implementiert.

Dies reduziert Abhängigkeiten und erleichtert Debugging, Tests und Weiterentwicklung.

---

# 3. Systemarchitektur

## 3.1 Komponentenübersicht

```text
                      USER
                       |
                       v
                +-------------+
                |  Streamlit  |
                |  Frontend   |
                +------+------+
                       |
                    REST API
                       |
                       v
                +-------------+
                |   FastAPI   |
                |   Backend   |
                +------+------+
                       |
          +------------+------------+
          |                         |
          v                         v
    +-----------+             +-----------+
    |  Qdrant   |             |  Ollama   |
    |           |             |           |
    | Vectors   |             | Embedding |
    | Metadata  |             | Chat LLM  |
    +-----------+             +-----------+

    +-------------------------------+
    | Persistent Document Storage   |
    | Original Files / Metadata     |
    +-------------------------------+
```

## 3.2 Verantwortlichkeiten

### Streamlit

Streamlit dient ausschliesslich als Benutzeroberfläche.

Verantwortlich für:

* Chat
* Dokumenten-Upload
* Dokumentenübersicht
* Dokumentenlöschung
* Modellauswahl
* Anzeige der Quellen
* Anzeige von Fehlern und Verarbeitungsstatus

Streamlit enthält keine eigentliche RAG-Geschäftslogik.

Die Kommunikation erfolgt ausschliesslich über die FastAPI REST API.

### FastAPI

FastAPI ist die zentrale Anwendungskomponente.

Verantwortlich für:

* API-Endpunkte
* Dokumentenverarbeitung
* Chunking
* Embedding-Generierung
* Speicherung und Suche
* Zusammenstellung des LLM-Kontexts
* Antwortgenerierung
* Quellenzuordnung
* Fehlerbehandlung

Die gesamte Geschäftslogik befindet sich im Backend.

### Qdrant

Qdrant übernimmt:

* Persistente Vektorspeicherung
* Speicherung von Chunk-Texten
* Speicherung von Chunk-Metadaten
* Similarity Search
* Metadatenfilterung
* Löschen indexierter Dokumentbestandteile

### Ollama

Eine bereits vorhandene Ollama-Instanz wird über HTTP angebunden.

Sie stellt zwei Funktionen bereit:

1. Embedding-Generierung
2. Chat Completion

Ollama gehört nicht zum initialen Docker-Compose-Stack.

---

# 4. RAG-Pipeline

Die Pipeline besteht aus zwei getrennten Abläufen.

## 4.1 Document Ingestion

Die Ingestion verarbeitet hochgeladene Dokumente und stellt deren Inhalte für die Suche bereit.

### Ablauf

```text
Document Upload
      |
      v
File Validation
      |
      v
Text Extraction
      |
      v
Text Normalization
      |
      v
Chunking
      |
      v
Embedding Generation
      |
      v
Qdrant Storage
      |
      v
Document Available
```

### Unterstützte Formate

| Format   | Verarbeitung            |
| -------- | ----------------------- |
| PDF      | pypdf                   |
| DOCX     | python-docx             |
| TXT      | Python Standard Library |
| Markdown | Python Standard Library |

Weitere Dateiformate sind zunächst nicht vorgesehen.

Insbesondere erfolgt keine OCR-Verarbeitung.

Gescannte PDFs ohne auslesbare Texte werden als nicht verarbeitbar gemeldet.

### Dateiverarbeitung

Jedes Dokument erhält:

* Eine eindeutige Dokument-ID
* Originaldateinamen
* Dateityp
* SHA-256-Hash
* Upload-Zeitpunkt
* Anzahl erzeugter Chunks
* Indexierungsstatus

Doppelte Uploads werden anhand des Datei-Hashes erkannt.

Identische Dateien werden innerhalb der bestehenden Dokumentensammlung nicht mehrfach indexiert.

### Chunking

Dokumente werden in kleinere, möglichst zusammenhängende Textabschnitte zerlegt.

Initiale Konfiguration:

| Parameter           | Wert                                 |
| ------------------- | ------------------------------------ |
| Zielgrösse          | ca. 600 Tokens                       |
| Overlap             | ca. 80 Tokens                        |
| Trennung            | Absätze und Überschriften bevorzugen |
| Seiteninformationen | Wenn verfügbar erhalten              |

Die Zielgrössen sind konfigurierbar.

Die Implementierung muss eine definierte Methode zur Abschätzung beziehungsweise Zählung von Tokens verwenden. Zeichenanzahl und Tokenanzahl dürfen nicht ungeprüft gleichgesetzt werden.

Chunks sollen möglichst keine Sätze oder Absätze unnötig auseinanderreissen.

### Embeddings

Die Embeddings werden über Ollama generiert.

Initial vorgesehen:

`embeddinggemma:300m`

Die Kommunikation erfolgt über:

```http
POST /api/embed
```

Das Embedding-Modell wird zentral im Backend konfiguriert.

Alle Vektoren innerhalb einer Qdrant-Collection müssen mit einer kompatiblen Embedding-Konfiguration erzeugt werden.

Ein Modellwechsel darf nicht unbemerkt bestehende Vektoren mit inkompatiblen Embeddings vermischen.

Für einen Modellwechsel ist eine kontrollierte Neuindexierung vorgesehen.

---

## 4.2 Retrieval & Generation

Beim Stellen einer Frage wird die RAG-Pipeline ausgeführt.

### Ablauf

```text
User Question
      |
      v
Question Embedding
      |
      v
Qdrant Similarity Search
      |
      v
Relevant Chunks
      |
      v
Context Assembly
      |
      v
LLM Prompt
      |
      v
Ollama Chat Model
      |
      v
Answer + Sources
```

### Retrieval

Initiale Parameter:

| Parameter       | Wert                |
| --------------- | ------------------- |
| Suchverfahren   | Dense Vector Search |
| Distanzmetrik   | Cosine              |
| Top-K           | 5                   |
| Hybrid Search   | Deaktiviert         |
| Reranking       | Deaktiviert         |
| Query Rewriting | Deaktiviert         |

Top-K bezeichnet die maximale Anzahl der Textabschnitte, die aus Qdrant abgerufen werden.

Die Parameter können später angepasst werden.

Das Backend soll die Retrieval-Ergebnisse unabhängig von der Antwortgenerierung bereitstellen können.

Dadurch kann überprüft werden, ob Fehler aus der Suche oder der LLM-Generierung stammen.

### Context Assembly

Die gefundenen Chunks werden zu einem strukturierten Kontext zusammengestellt.

Jeder Chunk enthält:

* Quellendokument
* Seitenzahl oder Abschnitt, sofern verfügbar
* Chunk-ID
* Textinhalt

Der Kontext wird anhand eines konfigurierbaren Budgets begrenzt, damit die verfügbare Kontextlänge des Chat-Modells nicht überschritten wird.

### Generation

Der Prompt enthält:

1. Systemanweisungen
2. Relevante Dokumentauszüge
3. Nutzerfrage

Das LLM soll:

* Antworten auf Grundlage des bereitgestellten Kontexts formulieren.
* Keine unbelegten Informationen als Dokumentenwissen darstellen.
* Fehlende oder unzureichende Informationen kenntlich machen.
* Quellen referenzieren.

Das Backend ordnet Quellenreferenzen den tatsächlich übergebenen Textabschnitten zu.

Eine Quellenangabe ist kein Beweis, dass die Aussage korrekt ist. Die zugrunde liegenden Textstellen müssen deshalb einsehbar bleiben.

---

# 5. Datenhaltung

## 5.1 Qdrant Collection

Für die erste Version genügt eine Collection für den aktiven Dokumentenindex.

Beispiel:

`rag_documents`

Die Collection speichert pro Chunk einen Vektor und zugehörige Metadaten.

### Payload-Beispiel

```json
{
  "document_id": "b0e4c5d2-...",
  "filename": "architecture.pdf",
  "content_hash": "abc123...",
  "chunk_index": 4,
  "page": 12,
  "section": "System Architecture",
  "text": "Die Architektur besteht aus...",
  "embedding_model": "embeddinggemma:300m"
}
```

Die Vektordimension wird anhand des verwendeten Embedding-Modells ermittelt.

Sie darf nicht als ungeprüfte Konstante festgelegt werden.

## 5.2 Originaldokumente

Originaldateien werden ausserhalb von Qdrant gespeichert.

Initialer Speicherort im Container:

```text
/app/data/documents/
```

Der Speicherort wird über ein persistentes Volume bereitgestellt.

Die Dateien bleiben nach Containerneustarts erhalten.

### Dokumenten-Metadaten

Zusätzlich wird ein einfaches Dokumentenregister benötigt, damit die Anwendung hochgeladene Dateien auch unabhängig von einzelnen Qdrant-Chunks verwalten kann.

Für Version 1 genügt eine kleine JSON-basierte Metadatenverwaltung auf dem persistenten Volume.

Dabei gelten folgende Einschränkungen:

* Eine aktive Backend-Instanz
* Kontrollierte, atomare Schreiboperationen
* Keine parallele Veränderung derselben Metadatendatei
* Konsistente Behandlung fehlgeschlagener Indexierungen

Eine zusätzliche relationale Datenbank wird zunächst nicht benötigt.

Bei künftigem Mehrbenutzerbetrieb oder mehreren Backend-Replikaten muss diese Lösung überprüft werden.

## 5.3 Datenkonsistenz

Folgende Operationen müssen vollständig und nachvollziehbar erfolgen:

* Dokument hinzufügen
* Dokument indexieren
* Dokument löschen
* Dokument erneut indexieren

Teilweise fehlgeschlagene Indexierungen dürfen nicht dazu führen, dass unvollständige Dokumente als erfolgreich indexiert gelten.

Beim Löschen eines Dokuments werden sowohl die Originaldatei als auch sämtliche zugehörigen Qdrant-Einträge entfernt.

Fehler müssen gemeldet und, soweit möglich, bereinigbar sein.

---

# 6. Backend API

Die API wird mittels FastAPI implementiert.

API-Präfix:

`/api/v1`

## 6.1 Dokumentenverwaltung

| Methode | Endpoint          | Funktion                          |
| ------- | ----------------- | --------------------------------- |
| POST    | `/documents`      | Dokument hochladen und indexieren |
| GET     | `/documents`      | Dokumente auflisten               |
| GET     | `/documents/{id}` | Dokumentinformationen abrufen     |
| DELETE  | `/documents/{id}` | Dokument vollständig löschen      |

Für Version 1 erfolgt die Indexierung synchron während des Uploads.

Die Benutzeroberfläche zeigt währenddessen einen Verarbeitungsindikator.

Dateigrösse und erlaubte Dokumentformate werden serverseitig begrenzt. Als initiale Obergrenze gelten 20 MB pro Datei.

Längere Indexierungen und Hintergrundverarbeitung können später ergänzt werden.

## 6.2 Suche

```http
POST /api/v1/search
```

Beispiel:

```json
{
  "query": "Wie funktioniert die Architektur?",
  "top_k": 5
}
```

Die Antwort enthält die gefundenen Chunks einschliesslich Metadaten und Similarity Scores.

Dieser Endpoint ist unabhängig vom Chat-Modell.

## 6.3 Chat

```http
POST /api/v1/chat
```

Beispiel:

```json
{
  "message": "Wie funktioniert die Architektur?",
  "model": "configured-chat-model",
  "top_k": 5
}
```

Beispielantwort:

```json
{
  "answer": "Die Architektur besteht aus...",
  "sources": [
    {
      "document_id": "b0e4c5d2-...",
      "filename": "architecture.pdf",
      "page": 12,
      "chunk_index": 4,
      "score": 0.89,
      "text": "Die Architektur besteht aus..."
    }
  ]
}
```

Der Chat-Endpoint übernimmt Retrieval und Generation.

Für Version 1 erfolgen die Antworten ohne Token-Streaming.

Eine Chat-Historie wird nur innerhalb der aktuellen Streamlit-Sitzung gehalten. Eine persistente Gesprächsdatenbank ist nicht vorgesehen.

## 6.4 Systeminformationen

| Endpoint             | Funktion                              |
| -------------------- | ------------------------------------- |
| `GET /health/live`   | Prüft, ob das Backend läuft           |
| `GET /health/ready`  | Prüft die Betriebsbereitschaft        |
| `GET /api/v1/models` | Listet verfügbare Ollama-Chat-Modelle |

FastAPI stellt zusätzlich automatisch die OpenAPI-Dokumentation bereit.

Diese ist während der Entwicklung über `/docs` erreichbar.

---

# 7. Frontend

Das Frontend verwendet Streamlit.

Die Oberfläche besteht aus drei Hauptbereichen.

## 7.1 Chat

Funktionen:

* Chat-Eingabe
* Anzeige der Antworten
* Auswahl des verfügbaren Chat-Modells
* Darstellung der verwendeten Quellen
* Anzeige der gefundenen Textstellen
* Zurücksetzen der Chat-Sitzung

Der Fokus liegt auf einfacher Bedienbarkeit.

## 7.2 Dokumente

Funktionen:

* Dokument hochladen
* Dokumentenliste anzeigen
* Dateityp und Grösse anzeigen
* Anzahl indexierter Chunks anzeigen
* Indexierungsstatus anzeigen
* Dokument löschen

## 7.3 Einstellungen

Initiale Einstellungen:

| Einstellung    | Funktion                    |
| -------------- | --------------------------- |
| Chat-Modell    | Ollama-Modell auswählen     |
| Top-K          | Anzahl Retrieval-Ergebnisse |
| Temperature    | Generierungsparameter       |
| Quellenanzeige | Textstellen ein-/ausblenden |

Das Embedding-Modell wird zunächst nicht über das Frontend gewechselt.

Dadurch vermeiden wir unbeabsichtigte Inkompatibilitäten innerhalb des Vektorindex.

---

# 8. Projektstruktur

Vorgeschlagene Repository-Struktur:

```text
local-rag/
│
├── backend/
│   ├── src/
│   │   └── rag/
│   │       ├── api/
│   │       │   ├── chat.py
│   │       │   ├── documents.py
│   │       │   ├── search.py
│   │       │   └── health.py
│   │       │
│   │       ├── ingestion/
│   │       │   ├── loader.py
│   │       │   ├── parser.py
│   │       │   ├── chunker.py
│   │       │   └── indexer.py
│   │       │
│   │       ├── retrieval/
│   │       │   └── retriever.py
│   │       │
│   │       ├── generation/
│   │       │   └── generator.py
│   │       │
│   │       ├── providers/
│   │       │   ├── ollama.py
│   │       │   └── qdrant.py
│   │       │
│   │       ├── storage/
│   │       │   └── documents.py
│   │       │
│   │       ├── config.py
│   │       └── main.py
│   │
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
│
├── frontend/
│   ├── app.py
│   ├── pages/
│   ├── Dockerfile
│   └── pyproject.toml
│
├── deploy/
│   └── compose.yaml
│
├── docs/
│   ├── VISION.md
│   └── SPEC.md
│
├── .env.example
├── .gitignore
└── README.md
```

Die Struktur trennt Frontend, Backend und Deployment.

Die Python-Module innerhalb des Backends bleiben Bestandteile einer einzigen Anwendung.

Es werden keine zusätzlichen Microservices eingeführt.

---

# 9. Konfiguration

Die Anwendung wird ausschliesslich über Umgebungsvariablen konfiguriert.

Beispiel:

```env
# Ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_CHAT_MODEL=
OLLAMA_EMBEDDING_MODEL=embeddinggemma:300m

# Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=rag_documents

# RAG
RAG_CHUNK_SIZE=600
RAG_CHUNK_OVERLAP=80
RAG_TOP_K=5
RAG_TEMPERATURE=0.2

# Storage
DOCUMENT_STORAGE_PATH=/app/data/documents

# Backend
BACKEND_URL=http://backend:8000
```

Die tatsächliche Ollama-Adresse hängt vom Hostsystem beziehungsweise Netzwerk ab.

`host.docker.internal` ist nicht auf allen Linux-Docker-Installationen automatisch verfügbar. Das Compose-Deployment muss die Erreichbarkeit entsprechend sicherstellen.

Das Chat-Modell wird aus den lokal verfügbaren Ollama-Modellen ausgewählt.

Konfigurationswerte werden beim Start validiert.

Passwörter und andere sensible Konfigurationswerte dürfen nicht im Repository gespeichert werden.

---

# 10. Docker Compose

## 10.1 Dienste

Der initiale Stack besteht aus drei Services:

```text
docker compose
│
├── frontend
│   └── Streamlit
│
├── backend
│   └── FastAPI
│
└── qdrant
    └── Vector Database
```

Ollama läuft ausserhalb des Stacks.

## 10.2 Kommunikation

Die Container kommunizieren über das interne Compose-Netzwerk.

| Verbindung          | Protokoll |
| ------------------- | --------- |
| Streamlit → FastAPI | HTTP      |
| FastAPI → Qdrant    | HTTP      |
| FastAPI → Ollama    | HTTP      |

Nur Streamlit muss vom Browser aus erreichbar sein.

Backend und Qdrant werden nicht öffentlich exponiert.

Für den lokalen Einzelplatzbetrieb wird Streamlit standardmässig ausschliesslich an `127.0.0.1` des Docker-Hosts gebunden.

## 10.3 Persistenz

Zwei persistente Speicherbereiche:

```text
qdrant_data
document_data
```

Diese speichern:

* Vektoren und zugehörige Payloads
* Originaldokumente
* Dokumentenregister

Qdrant benötigt geeigneten persistenten Blockspeicher mit kompatiblem Dateisystem. Ein gewöhnliches NFS-Volume ist dafür nicht vorgesehen.

## 10.4 Betrieb

Die Anwendung muss mit folgenden Befehlen nutzbar sein:

```bash
docker compose up -d
```

```bash
docker compose down
```

```bash
docker compose logs -f
```

Ein normaler Containerneustart darf keine indexierten Dokumente verlieren.

Das Deployment muss reproduzierbar sein.

---

# 11. Kubernetes-Kompatibilität

Kubernetes wird zunächst nicht implementiert.

Die Architektur wird jedoch so aufgebaut, dass eine spätere Migration nach k3s oder Kubernetes ohne grundlegende Änderungen an der Anwendung möglich bleibt.

### Vorgaben

**Stateless Frontend**

Streamlit speichert keine persistenten Geschäftsdaten.

**Backend ohne Container-lokale Persistenz**

Persistente Dokumentdaten liegen ausschliesslich auf einem konfigurierten Volume.

**Konfigurierbare Service-Adressen**

Keine fest codierten Hostnamen oder IP-Adressen.

**Health Checks**

Geeignete Endpunkte für Kubernetes Liveness und Readiness Probes.

**Containerunabhängigkeit**

Keine Abhängigkeit von Docker-Socket, Compose-Kommandos oder Docker-spezifischen APIs.

**Persistent Storage**

Qdrant und Dokumente verwenden später Kubernetes PersistentVolumeClaims.

**Initial eine Backend-Instanz**

Die erste Version benötigt nur eine Instanz des Backends.

Eine horizontale Skalierung wird nicht vorausgesetzt, da die einfache dateibasierte Metadatenverwaltung dafür noch nicht geeignet ist.

### Zielabbildung

| Compose           | Kubernetes            |
| ----------------- | --------------------- |
| Streamlit Service | Deployment            |
| FastAPI Service   | Deployment            |
| Qdrant Service    | StatefulSet           |
| Docker Volume     | PersistentVolumeClaim |
| Environment       | ConfigMap / Secret    |
| Compose Network   | Kubernetes Services   |

Eine Migration der persistenten Daten muss separat geplant und getestet werden.

---

# 12. Sicherheit und Betrieb

Die erste Version ist für eine vertrauenswürdige lokale Umgebung vorgesehen.

### Sicherheitsanforderungen

* Kein direkter öffentlicher Zugriff auf Qdrant.
* Kein direkter öffentlicher Zugriff auf FastAPI.
* Keine externe Übermittlung von Dokumenten.
* Dateityp und Dateigrösse werden geprüft.
* Hochgeladene Dateinamen dürfen keine unkontrollierten Dateipfade erzeugen.
* Originaldateien werden unter internen IDs gespeichert.
* API-Fehler dürfen keine sensiblen Konfigurationswerte offenlegen.

Eine Benutzerverwaltung ist nicht Bestandteil von Version 1.

**Wichtig:** Ohne Authentifizierung darf die Anwendung nicht ungeschützt im öffentlichen Netzwerk betrieben werden.

Ein späterer Netzwerkzugriff erfordert geeignete Zugangskontrollen.

### Logging

Das Backend verwendet strukturiertes Logging.

Mindestens protokolliert werden:

* Dokumenten-Upload
* Indexierungsergebnis
* Fehler bei der Verarbeitung
* Ollama-Verbindungsfehler
* Qdrant-Verbindungsfehler
* Dauer von Retrieval und Generation

Vollständige Dokumentinhalte und Nutzerfragen werden standardmässig nicht protokolliert.

### Backups

Für einen wiederherstellbaren Zustand müssen gesichert werden:

* Originaldokumente
* Dokumentenregister
* Qdrant-Daten beziehungsweise konsistente Qdrant-Snapshots
* Relevante Konfiguration

Eine reine Sicherung der Qdrant-Daten genügt nicht.

---

# 13. Qualitätssicherung

## 13.1 Entwicklungswerkzeuge

| Bereich         | Werkzeug       |
| --------------- | -------------- |
| Paketverwaltung | uv             |
| Tests           | pytest         |
| Linting         | Ruff           |
| Formatierung    | Ruff           |
| Typprüfung      | Mypy           |
| API-Tests       | pytest + httpx |

Automatisierte Tests sollen ohne laufendes LLM möglich sein.

Dazu werden Ollama und Qdrant in Unit-Tests durch geeignete Testimplementierungen beziehungsweise Mocks ersetzt.

Integrationstests prüfen die Kommunikation mit den tatsächlichen Diensten.

## 13.2 Testbereiche

**Ingestion**

* Unterstützte Dokumentformate
* Leere Dokumente
* Ungültige Dateien
* Doppelte Uploads
* Chunking
* Metadaten
* Fehlgeschlagene Indexierungen

**Retrieval**

* Korrekte Embedding-Anfragen
* Similarity Search
* Top-K-Begrenzung
* Metadatenzuordnung
* Keine Treffer

**Generation**

* Korrekte Kontextzusammenstellung
* Quellenreferenzen
* Fehlerhafte oder nicht erreichbare LLMs
* Fehlender Kontext

**Persistenz**

* Containerneustart
* Dokumentenlöschung
* Wiederherstellung vorhandener Daten

## 13.3 RAG-Qualität

Zusätzlich wird ein kleiner Evaluationsdatensatz angelegt.

Initial:

15–20 Fragen zu bekannten Testdokumenten.

Die Testfragen sollen Fälle enthalten, in denen:

* Eine eindeutige Antwort vorhanden ist.
* Mehrere Dokumentstellen relevant sind.
* Keine Antwort in den Dokumenten vorhanden ist.
* Fachbegriffe oder konkrete Bezeichnungen gesucht werden.

Bewertet werden insbesondere:

1. Werden die richtigen Textstellen gefunden?
2. Sind die Quellen korrekt zugeordnet?
3. Ist die Antwort durch den Kontext gedeckt?
4. Werden unbelegte Aussagen vermieden?

Die Ergebnisse bilden eine Baseline für spätere Optimierungen.

---

# 14. Initialer Vertical Slice

## Ziel

Ein Nutzer kann lokal Dokumente hochladen und anschliessend Fragen dazu stellen.

Die Antworten basieren auf den indexierten Inhalten und enthalten überprüfbare Quellenangaben.

## Umfang

Der erste Vertical Slice umfasst:

1. Docker-Compose-Deployment
2. Streamlit-Oberfläche
3. FastAPI-Backend
4. Verbindung zur bestehenden Ollama-Instanz
5. Qdrant-Integration
6. Dokumenten-Upload und Textextraktion
7. Chunking und Embedding-Generierung
8. Vektorspeicherung
9. Similarity Search
10. RAG-basierte Antwortgenerierung
11. Quellenanzeige
12. Dokumentenverwaltung
13. Persistente Speicherung
14. Automatisierte Tests

## Definition of Done

| Kriterium     | Erwartetes Ergebnis                                                   |
| ------------- | --------------------------------------------------------------------- |
| Start         | Anwendung startet mit Docker Compose                                  |
| Ollama        | Bestehende Instanz wird erfolgreich verwendet                         |
| Dokumente     | PDF, DOCX, TXT und Markdown funktionieren                             |
| Ingestion     | Dokumente werden verarbeitet und indexiert                            |
| Speicherung   | Vektoren und Metadaten liegen in Qdrant                               |
| Retrieval     | Relevante Textstellen werden zurückgeliefert                          |
| Chat          | Fragen werden mit Dokumentkontext beantwortet                         |
| Quellen       | Verwendete Textstellen sind einsehbar                                 |
| Löschen       | Dokumente und zugehörige Indexeinträge werden entfernt                |
| Fehler        | Fehlerhafte Dokumente und Dienstausfälle werden verständlich gemeldet |
| Persistenz    | Neustarts erhalten den Datenbestand                                   |
| Tests         | Automatisierte Tests erfolgreich                                      |
| Portabilität  | Keine unnötigen Docker-Compose-Abhängigkeiten im Anwendungscode       |
| Dokumentation | Setup und Betrieb sind im README beschrieben                          |

---

# 15. Nicht Bestandteil der ersten Version

Folgende Funktionen werden bewusst zurückgestellt:

* Benutzerverwaltung und Rollen
* Cloud-LLMs
* Web-Crawling
* Automatische Dateisystemüberwachung
* OCR
* Multimodales RAG
* GraphRAG
* Hybrid Search
* Reranking
* KI-Agenten
* Persistente Chat-Historie
* Verteilte Hintergrundverarbeitung
* Message Queues
* Horizontale Skalierung
* Kubernetes-Deployment
* Umfangreiches Monitoring
* Automatische Modellbewertung

Diese Funktionen dürfen später ergänzt werden, sind aber keine Voraussetzung für die erste produktiv nutzbare Version.

---

# 16. Entwicklungsgrundsätze

Für die Implementierung gelten folgende Regeln:

**1. Funktionierende Vertical Slices**

Keine umfangreiche Infrastruktur ohne unmittelbar nutzbare Funktionalität.

**2. Kleine, verständliche Module**

Keine unnötigen Abstraktionen oder Framework-Schichten.

**3. Trennung der Verantwortlichkeiten**

Streamlit ist UI, FastAPI enthält Geschäftslogik, Qdrant speichert und sucht, Ollama stellt KI-Funktionen bereit.

**4. Nachvollziehbarkeit vor Komplexität**

Retrieval-Ergebnisse müssen sichtbar und überprüfbar sein.

**5. Austauschbarkeit statt Framework-Abhängigkeit**

Externe Komponenten werden über klar definierte Schnittstellen angebunden.

**6. Reproduzierbarkeit**

Versionen, Konfigurationen und Tests sind dokumentiert.

**7. Schrittweise Erweiterung**

Weitere Funktionen werden erst eingeführt, wenn ein konkreter Bedarf oder ein nachgewiesenes Problem besteht.

---

## Zusammenfassung

Local RAG wird als kleine, modular aufgebaute Python-Anwendung entwickelt.

Der erste Stand verwendet:

* **Streamlit** für die Benutzeroberfläche
* **FastAPI** für die RAG-Orchestrierung
* **Qdrant** für Vektoren und Metadaten
* **Ollama** für Embeddings und lokale LLMs
* **Docker Compose** für den initialen Betrieb

Die Architektur bleibt bewusst einfach, nachvollziehbar und unabhängig von einer bestimmten Container-Orchestrierung.

**Ziel ist kein möglichst umfangreiches RAG-Framework, sondern ein zuverlässiges, kontrollierbares und langfristig erweiterbares lokales RAG-System.**

