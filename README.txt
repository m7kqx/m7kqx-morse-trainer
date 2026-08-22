# M7KQX Morse Trainer v1.5 - Alpha Test

## Hardware Requirements
This trainer is built specifically to interface with the **Open CW Keyer (K3NG firmware)**. 

## K3NG Firmware Configuration
For the application to read your paddle input, your keyer must be configured to echo decoded ASCII characters over the serial port at 115200 baud. 

Ensure the following flags are active in your `keyer_features_and_options.h` file before compiling and uploading to your keyer:

*   `#define FEATURE_COMMAND_LINE_INTERFACE` (Required to output readable text)
*   `#define OPTION_PROG_MEM_TRIM` (Often needed on Nano/Uno to fit the CLI feature into memory)

Ensure the default CLI baud rate is set to `115200` in `keyer_settings.h`.

## Running the Application
No installation or Python environment is required. Simply run the executable provided for your operating system. Connect your keyer via USB before launching the application. 

**Linux / Raspberry Pi OS Note:** 
You may need to mark the downloaded file as executable before it will run:
`chmod +x morse_trainer_v1_5`

Ensure your user account has permission to access serial ports:
`sudo usermod -a -G dialout $USER`