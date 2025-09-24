# Sync-Mate-API-WS 🌐

[![Project Status](https://img.shields.io/badge/Status-Development-yellow)]()
[![Python](https://img.shields.io/badge/Python-3.11-%233776AB?logo=python)](https://python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.2-%2300B4D8?logo=fastapi)](https://fastapi.tiangolo.com/)
[![WebSocket](https://img.shields.io/badge/WebSocket-Real--time-1C1C1C?logo=websocket)]()
[![License](https://img.shields.io/badge/License-MIT-green)](https://opensource.org/licenses/MIT)

**Sync-Mate-API-WS** is a Python WebSocket API service built with FastAPI, designed for real-time synchronized video
watching. It allows multiple users to watch videos together from sites like Rezka, YouTube, or your own platform,
keeping playback perfectly in sync.

> ⚠️ Project is currently under development.

---

## ✨ Core Features

* **Real-time Video Sync**
    * 🌐 WebSocket-based instant synchronization for multiple users
    * 🎬 Supports YouTube, Rezka, and custom video sources
    * 🔄 Keeps playback, pause, and seek actions in sync across clients

* **API Management**
    * 🧩 Extendable WebSocket endpoints

* **User Collaboration**
    * 👥 Join and leave rooms dynamically
    * 📢 Broadcast events to all participants in a room

* **Development Friendly**
    * 🧪 Easy to test with Pytest
    * ⚙️ Dependency management via Poetry

---

## 🧰 Tech Stack

* **Backend**: Python 3.11+, FastAPI
* **Real-time Communication**: WebSockets
* **Package Management**: Poetry
* **Testing**: Pytest
* **Serialization**: JSON

---

## ⚙️ Installation & Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/Zebaro24/Sync-Mate-API-WS.git
   cd Sync-Mate-API-WS
   ```

2. **Install dependencies with Poetry**

   ```bash
   poetry install
   ```

3. **Activate the virtual environment**

   ```bash
   poetry shell
   ```

---

## 🚀 Running the Server

```bash
uvicorn app.main:app --reload
```

*By default, the API will run at `http://127.0.0.1:8000`.*

---

## 🧪 Testing

```bash
poetry run pytest
```

Run all project tests and check functionality.

---

## 📬 Contact

- **Developer**: Denys Shcherbatyi
- **Email**: zebaro.work@gmail.com
