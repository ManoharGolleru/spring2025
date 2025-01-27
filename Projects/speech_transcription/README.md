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



This repository contains code for a ROS-enabled webpage.  This is not a polished product; it's designed to provide some starter code to highlight these types of interactivity:
- "Touchpad" controls on mobile devices.  These can be used, for example, to control drones.
- "Direction Pad" controls (on mobile and desktop).  These are discrete buttons, like "move forward" or "stop".
- Support for gamepads (like XBox or PS5 controllers).  Connect your gamepad to your phone/computer and press a button.  The gamepad should be instantly recognized.
- Support for speech-to-text via the Whisper API.  This has been successfully tested on Android and Ubuntu devices.  It fails to work on Mac/iOS devices.  I don't do Windows.
- Video streams from ROS compressed image topics, or mjpg streams.
- A "console" to display messages.  The system can be run on a network with multiple users in "chat" mode.

![image](https://github.com/optimatorlab/ub_web/assets/18486796/2fc5222f-4ca8-4c0c-aaad-3043c5e6d339)


The idea is to make it "easy" for students to control robots via
- Physical external gamepad/joystick (e.g., an XBox controller)
- Voice ([Whisper speech-to-text](https://github.com/openai/whisper))
- Text
- Webpage buttons/sliders

Although the backend (web server and ROS components) must be on a ROS-capable computer (we use Ubuntu 20.04 at the moment), the end user just needs a web browser.



## Installation

**NOTE: This has only been tested on ROS Noetic running on Ubuntu 20.04, with Chromium/Chrome web browers.**

### Install [Whisper](https://github.com/openai/whisper), the OpenAI speech-to-text model.
This is optional, but is highly recommended.  It is free, no API-key, and runs locally on your machine.

As of the moment this file was written, `v20231117` was the latest version.  You may wish to experiment with a newer version, should one be released in the future.
```
pip install openai-whisper==20231117
```

You'll also need `ffmpeg`.  If it's not already installed on your machine:
```
sudo apt update && sudo apt install ffmpeg
```

