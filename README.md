## 🚀 Guía Rápida: Arranque del Entorno (Para el equipo de desarrollo)

¡Hola equipo! Para asegurar que todos trabajamos con la misma configuración y evitar subir claves por error a GitHub, seguid estos pasos exactos antes de ejecutar el código:

### 1. Clonar el repositorio y activar el entorno
Clona el repositorio en tu máquina local.
Si utilizas **Linux o macOS**, activa el entorno virtual ejecutando:
`source venv/bin/activate`

*(Si alguien del equipo utiliza Windows, el comando es `venv\Scripts\activate`)*.

### 2. Instalar las dependencias
El proyecto utiliza un archivo `requirements.txt` para garantizar que todos tenemos las mismas versiones de Google ADK, CrewAI, etc. Instala todo de golpe con:
`pip install -r requirements.txt`

### 3. Configurar las Claves API (.env)
Por motivos de seguridad, las claves API **nunca** deben subirse al repositorio. 
Debéis crear un archivo nuevo llamado **`.env`** en la raíz del proyecto (al mismo nivel que `agent.py`).

Abrid el archivo `.env` y añadid las credenciales de PoliGPT con este formato exacto:

POLI_API_KEY=vuestra_clave_aqui
POLI_API_BASE=el_enlace

Tenéis tanto la clave como el enlace en los ejemplos de agent.py del profesor, en la llamada "model = LittleLlm()".

*(Nota: El archivo `.gitignore` ya está configurado para ignorar este archivo automáticamente).*

### 4. Ejecutar el Agente
Una vez configurado el entorno y las claves, podéis probar el agente levantando la interfaz web del ADK:
`adk web`
