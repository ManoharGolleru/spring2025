#!/usr/bin/env bash

# Refresh .bashrc to get the appropriate/up-to-date IP addresses
# source ${HOME}/.bashrc
# FIXME 1 -- Need to document in the README the important/relevant items from the .bashrc file
# FIXME 2 -- What to do for Windows?  This `bash` script isn't going to work, right?  Need a `.bat` script, or something like that?

sleep 1s

# I this this was ROS-specific:
# Export the ROS IP address to be used in Web page:
# CURRENT_IP_FILE="${HOME}/catkin_ws/src/cog/html/scripts/currentIP.js"
# echo "// Updated by cog-start, with hard-coded IP address" > $CURRENT_IP_FILE
# echo "// ${ROS_HOSTNAME}" >> $CURRENT_IP_FILE
# echo "var ROS_IP = 'wss://${ROS_HOSTNAME}:9090';" >> $CURRENT_IP_FILE
# echo "var HOST_IP = '${ROS_HOSTNAME}';" >> $CURRENT_IP_FILE


# FIXME 3 -- Need to document the directory structure.
#            Filepaths are hard-coded below

# Start node.js web server
SCRIPT1="node server_secure.cjs --public"
gnome-terminal --tab --title "NODE.JS" --working-directory=${HOME}/Projects/speech_transcription/html -- bash -ic "export HISTFILE=${HOME}/.bash_history_junk1; $SCRIPT1; history -s $SCRIPT1; exec bash" 

# Start WhisperLive Server
SCRIPT2="python3 run_server.py --port 9091 --backend faster_whisper"
gnome-terminal --tab --title "FASTER_WHISPER" --working-directory=${HOME}/Projects/speech_transcription/scripts -- bash -ic "export HISTFILE=${HOME}/.bash_history_junk2; $SCRIPT2; history -s $SCRIPT2; exec bash" 

# Start our main.py node:
SCRIPT3="python3 main.py"
gnome-terminal --tab --title "MAIN.PY" --working-directory=${HOME}/Projects/speech_transcription/scripts -- bash -ic "export HISTFILE=${HOME}/.bash_history_junk3; $SCRIPT3; history -s $SCRIPT3; exec bash" 


# Start chromium
sleep 5s
# chromium "https://${HOST_IP}:8080/"
# firefox "https://localhost:8080/"
chromium "https://localhost:8080/"


# Print some info to the screen
echo "Admin: Visit https://localhost:8080/admin.html"
echo "User:  Visit https://localhost:8080/index.html"
