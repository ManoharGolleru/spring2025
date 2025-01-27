# A Simple Browser - Using `socket.io`

In this project, you will have a 
- secure server (https vs http)
- Visit https://localhost:8080 (or, if you know your IP address, https://<ip address>:8080)
- Pass messages/data between Python and JavaScript

--- 

## Installation

### 1.  Install `Node.JS`
- Visit https://nodejs.org/en
- Follow the installation instructions for your operating system


### 2. Clone or Download This Repository
The easiest way to get this code is to visit https://github.com/IE-482-582/spring2025, click the green `Code` button, and download a ZIP of the repository.

If you're comfortable using the command line (terminal), you may navigate to a location where you want to save the code and then
```
git clone https://github.com/IE-482-582/spring2025.git
```
- QUESTION:  What is the equivalent command for Windows users?

### 3. In Case of Issues
If you get errors when running the project (see steps below), you may need to explictly install these `Node.JS` dependencies.

You will need to run these commands from the directory where the `server_secure.cjs` file is saved.
```
npm install express@4
npm install socket.io
npm install compression
npm install request
npm install yargs
```

---

## Running the Project
You will need 2 terminal windows.  In both of them, change directories to the `simple_browser_socket` folder.
- Terminal 1:
    ```
    node server_secure.cjs --public
    ```
- Terminal 2:
    ```
    python3 client.py
    ```
    
Now, open your browser to https://localhost:8080/index.html


---

## What's Happening?

*to be determined*

*Explain what `Node.JS` is providing*

*What "topics" are being published?  Who is publishing them?  Who is subscribing?*

*What is `index.html` doing?*

*What is `client.py` doing?*


   
 
---

## Resources
These are the primary ones:
- https://socket.io/docs/v4/tutorial/introduction
- https://python-socketio.readthedocs.io/en/stable/intro.html


Other stuff I looked at:
- https://github.com/miguelgrinberg/python-socketio/issues/334
- https://stackoverflow.com/questions/51390968/python-ssl-certificate-verify-error
- https://stackoverflow.com/questions/39184455/connect-js-client-with-python-server
- https://stackoverflow.com/questions/61154295/how-can-i-connect-a-javascript-client-to-a-python-socketio-server
