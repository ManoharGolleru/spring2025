# A Simple Speech-to-Text Transcription Service

This project provides a serviceable speech-to-text transcription that operates close to real-time.

The speech-to-text capability is provided by [WhisperLive](https://github.com/collabora/WhisperLive/tree/main).

## Installation
- Install WhisperLive (see https://github.com/collabora/WhisperLive/tree/main)
- Install Node.JS and the modules required by our [`simple_browser_socket`] demo

## Running the System - Manual
You will need 3 terminals.  Change directories to the `speech_transcription` folder.
- Terminal 1 - Start `node` server:
    ```
    cd html
    node server_secure.cjs --public
    ```

- Terminal 2 - Start WhisperLive server:
    ```
    cd scripts
    python3 run_server.py --port 9091 --backend faster_whisper
    ```
    
- Terminal 3 - Start the Python code for processing data:
    ```
    cd scripts
    python3 main.py
    ```
    
Now, there are two Web pages to open:
- https://localhost:8080/admin.html -- Choose mic, start/stop transcription
- https://localhost:8080/index.html -- Watch transcription


## Running the System - Scripted
Change directories to the `speech_transcription` folder.
```
./start.sh
```


