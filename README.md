# actiCHampConnect

actiCHampConnect connects MATLAB or Python directly to a Brain Products actiCHamp (Plus) amplifier. It reads the electrode impedances and the EEG data without BrainVision Recorder, LSL or any other additional software.

It was developed with a 32-channel actiCHamp Plus on Windows.

## Contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Folder structure](#folder-structure)
- [MATLAB program](#matlab-program)
- [Python program](#python-program)
- [Data format](#data-format)
- [What is implemented and what is not](#what-is-implemented-and-what-is-not)
- [Changing and compiling the C++ code](#changing-and-compiling-the-c-code)
- [Troubleshooting](#troubleshooting)
- [License and third-party components](#license-and-third-party-components)

## How it works

The amplifier can only be reached through the Brain Products Amplifier SDK, which is a C++ library. A small C++ program, the **producer**, therefore does the talking to the amplifier. MATLAB and Python only start this program and exchange data with it through a block of shared memory.

```
 actiCHamp  --USB-->  EEG_SharedMemoryProducer.exe  -->  shared memory  -->  MATLAB (MEX functions)
                      (C++, Amplifier SDK)               "EEG_SharedMemory"  Python (ctypes)
```

A measurement always runs through the same three phases:

1. **Connect.** MATLAB or Python starts the producer. The producer opens the first amplifier it finds on USB and immediately starts measuring impedances.
2. **Impedance.** The producer keeps writing the latest impedance values into the shared memory. You can read them as often as you like.
3. **Acquisition.** As soon as you set a sampling rate, the producer stops the impedance measurement and streams the samples into a ring buffer in the shared memory. You read the samples from there. Stopping the producer releases the amplifier.

The amplifier cannot measure impedance and record EEG at the same time. Once the acquisition runs, you have to disconnect and connect again to see impedances.

## Requirements

- Windows 10 or 11, 64 bit.
- A Brain Products actiCHamp or actiCHamp Plus, connected via USB and powered. The Brain Products USB driver must be installed. It comes with BrainVision Recorder or the actiCHamp driver package.
- No other program may use the amplifier at the same time, for example BrainVision Recorder or the actiCHamp LSL connector.
- MATLAB: tested with R2025b. The MEX functions are included already compiled, so no compiler is needed to run the example.
- Python: 3.9 or newer, 64 bit, with the packages in `Python/requirements.txt`.

A C++ compiler and the Brain Products Amplifier SDK are only needed if you want to change the C++ code. See [Changing and compiling the C++ code](#changing-and-compiling-the-c-code).

## Folder structure

| Folder | Content |
|---|---|
| `Producer/` | The producer `EEG_SharedMemoryProducer.exe`, its source code, the build script and the Brain Products libraries it needs at run time. This folder is used by MATLAB and by Python. |
| `MATLAB/` | Example `main.m`, the connect and disconnect functions and the MEX functions with their source code. |
| `Python/` | Example `__main__.py` and the module `actiCHampConnect.py`. |

Keep the three folders next to each other. Both examples look for the producer in `../Producer`.

## MATLAB program

Open the `MATLAB` folder in MATLAB and run `main.m`.

1. Set the sampling rate, the recording time and how long the impedances are shown.
2. `ActiCHampConnect` starts the producer. The amplifier now measures impedances.
3. `GetImpedances` returns the latest impedance values. The example prints them once per second.
4. `WriteFs` sets the sampling rate. This ends the impedance measurement and starts the data stream.
5. `ReadHybridMemory` returns the requested number of samples.
6. Process the data as needed.
7. `ActiCHampDisconnect` stops the producer and releases the amplifier.

| Function | Type | Description |
|---|---|---|
| `proc = ActiCHampConnect(producerDir, timeout)` | `.m` | Starts the producer and waits until the shared memory exists. |
| `ActiCHampDisconnect(proc, timeout)` | `.m` | Stops the producer. Kills it if it does not stop in time. |
| `imp = GetImpedances()` | MEX | Latest impedances in Ohm. Empty if nothing was measured yet. |
| `WriteFs(fs)` | MEX | Sets the sampling rate in Hz and thereby starts the acquisition. |
| `data = ReadHybridMemory(n)` | MEX | Waits until `n` samples are available and returns them as an `n` x 43 matrix. |
| `ClearSharedBuffer()` | MEX | Empties the ring buffer. Use it to throw away old samples before a new recording block. |
| `StopProducer()` | MEX | Asks the producer to stop. Called by `ActiCHampDisconnect`. |

`ReadHybridMemory` blocks MATLAB until all requested samples have arrived, and it cannot be interrupted with Ctrl+C. Read long recordings in blocks, for example one second at a time.

## Python program

1. Install the requirements.
```bash
cd Python
pip install -r requirements.txt
```
2. Set the sampling rate, the recording time and how long the impedances are shown in `__main__.py`.
3. Run the script.
```bash
python __main__.py
```
4. The script starts the producer using `ActiCHampDevice` from `actiCHampConnect.py`.
5. It prints the impedances once per second with `get_impedances()`.
6. It starts the acquisition with `start_acquisition(fs)` and fetches the data with `get_data(samples)`.
7. It stops the producer with `disconnect()`.

| Method | Description |
|---|---|
| `ActiCHampDevice(producer_dir, timeout)` | Both arguments are optional. Default is the `Producer` folder of this repository and 10 seconds. |
| `connect()` | Starts the producer and attaches to the shared memory. |
| `get_impedances(wait=True)` | Latest impedances in Ohm as a NumPy array. Raises an error after `start_acquisition`. |
| `start_acquisition(fs)` | Sets the sampling rate in Hz and waits until the amplifier streams. |
| `get_data(samples)` | Waits until `samples` samples are available and returns them as a `samples` x 43 array. |
| `clear_buffer()` | Throws away all samples that are waiting in the ring buffer. |
| `lost_samples()` | Number of samples the producer had to drop because the ring buffer was full. |
| `disconnect()` | Stops the producer and releases the amplifier. |

The producer opens its own console window when it is started from Python, as in MATLAB. It shows the amplifiers found and the applied sampling rate, and closes when the producer stops.

## Data format

### Impedances

`GetImpedances()` and `get_impedances()` return 45 values in **Ohm**.

| Index MATLAB | Index Python | Content |
|---|---|---|
| 1 | 0 | Ground electrode (GND) |
| 2 | 1 | Reference electrode (REF) |
| 3-34 | 2-33 | EEG channels 1-32 |
| 35-45 | 34-44 | Not used on a 32-channel amplifier |

A value of -1 means that no impedance is available for this entry. The values are updated continuously while the amplifier is in the impedance phase.

### EEG data

`ReadHybridMemory(n)` and `get_data(n)` return one row per sample and 43 columns. The producer copies the enabled amplifier channels in the order the amplifier delivers them. Each value is already scaled with the resolution of its channel.

| Columns MATLAB | Columns Python | Content | Unit |
|---|---|---|---|
| 1-32 | 0-31 | EEG channels 1-32 | µV |
| 33-40 | 32-39 | AUX channels 1-8 | µV |
| 41-43 | 40-42 | Remaining channels of the amplifier. Not verified, see below. | - |

This table is valid for a 32-channel actiCHamp (Plus). The meaning of columns 41-43 has not been checked.

### Sampling rate

The producer maps the requested sampling rate to the nearest of these values: 100, 200, 500, 1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000 and 100000 Hz. The rate that was really applied is printed by the producer as `Requested Fs: ... Hz, Applied Fs: ... Hz`.

### Ring buffer and lost samples

The ring buffer holds 200000 samples. That is 200 seconds at 1000 Hz, but only 2 seconds at 100000 Hz. If you read slower than the amplifier writes, the producer overwrites the oldest samples and counts them. Read the data in a loop without long pauses at high sampling rates.

## What is implemented and what is not

Implemented:

- Starting and stopping the producer from MATLAB and Python.
- Connecting to the first actiCHamp found on USB.
- Continuous impedance measurement of GND, REF and all EEG channels before the recording.
- Data acquisition of the EEG and AUX channels with a selectable sampling rate.
- Loss-free reading through a ring buffer, including a counter for dropped samples.

Not implemented:

- **Impedance during or after a recording.** The producer measures impedances only until the sampling rate is set. To measure again, disconnect and connect again.
- **Changing the sampling rate while running.** The rate can be set once per connection.
- **The control flags in `SharedBuffer.h`.** The control block already contains flags such as `useActiveElectrodes`, `measureImpedance` or `enableNotchFilter`. They are placeholders. The producer does not read any of them.
- **Selecting channels.** The producer always uses the channels that are enabled in the amplifier by default.
- **More than 43 channels.** Amplifiers with 64 or more channels need a larger `MAX_CHANNELS`, see below.
- **Fewer than 43 channels.** The producer always copies 43 values per sample. If the amplifier delivers fewer channels, the remaining columns contain undefined values.
- **Trigger and marker decoding.** Trigger inputs are not decoded into events.
- **The sample counter of the amplifier.** It is not passed on.
- **Choosing between several amplifiers.** Always the first one found is used.
- **Saving data to a file.** Do this in MATLAB or Python.
- **Reading the lost sample counter in MATLAB.** There is no MEX function for it yet. Python has `lost_samples()`.
- **A timeout in `ReadHybridMemory`.** The MATLAB function waits without limit.
- **Linux and macOS.** The SDK and the shared memory code are Windows only.

## Changing and compiling the C++ code

There are two kinds of C++ code. The producer is a normal program. The MEX functions are small MATLAB extensions. Both include `Producer/SharedBuffer.h`, which defines the layout of the shared memory.

### The files

| File in `Producer/` | Purpose |
|---|---|
| `EEG_SharedMemoryProducer.cpp` | **The main C++ file.** Connects to the amplifier, measures impedances, acquires data and writes it to the shared memory. |
| `SharedBuffer.h` | Layout of the shared memory: ring buffer, control block, impedances. |
| `AmplifierSDK.dll`, `ActiChamp_x64.dll`, `actiCHampLib.dll` | Libraries of the Brain Products Amplifier SDK. Needed at run time next to the `.exe`. |
| `ActiChamp.bit`, `ActiChampX.bit` | Firmware that the SDK loads into the amplifier. Needed at run time next to the `.exe`. |
| `ActiChamp_x64.dll.ini` | Settings of the SDK library. Leave `Emulation=0`. |
| `build.bat` | Builds the producer. |

The SDK files that are needed for compiling are not included, see [Getting the Amplifier SDK](#getting-the-amplifier-sdk).

### Where to change what

The steps in `main()` of `EEG_SharedMemoryProducer.cpp` are numbered in the comments.

| You want to change | Look at |
|---|---|
| The supported sampling rates | `ChangeSampleRate()`, list `allowedRates` |
| Which amplifier is opened | `ConnectToAmp(0)` in `main()`, the argument is the device index |
| How impedances are measured or ordered | The `impedanceThread` in step 4 of `main()` |
| What is written per sample | `DataAcquisitionThread()` |
| Amplifier settings such as active shield gain or channel enabling | Add `amp.SetProperty(...)` calls after `ConnectToAmp(0)`. `BasicExample.cpp` and `AmplifierSDK.chm` in the SDK folder show the available properties. |
| Number of columns or length of the ring buffer | `MAX_CHANNELS` and `BUFFER_SIZE` in `SharedBuffer.h` |

### Getting the Amplifier SDK

The SDK headers, the import library, the documentation and the samples are not part of this repository, because their license does not allow passing them on. You only need them to compile the producer. Running the examples works without this step.

1. Open https://www.brainproducts.com/downloads/more-software/ and go to **Software Development Kits**.
2. Download the **BrainVision Amplifier SDK** for actiCHamp, actiCHamp Plus and LiveAmp. You have to accept the licensing terms of Brain Products first.
3. Run the installer and keep the default folder `C:\Vision\Amplifier SDK`.

This project was built with SDK version 1.1.0.2. The build script takes these files directly from the SDK folder, so nothing has to be copied:

| File in the SDK folder | Purpose |
|---|---|
| `Include\SDK.h`, `Include\AmplifierSDK.h`, `Include\Amplifier_LIB.h` | Headers of the SDK. |
| `Samples\C++\RawDataHandlerExample.h` | Sample code that converts the raw amplifier bytes into scaled values. |
| `Bin\x64\AmplifierSDK.lib` | Import library for linking. |
| `Docs\AmplifierSDK.chm` | Documentation of all properties and functions of the amplifier. |
| `Samples\C++\BasicExample\BasicExample.cpp` | Example from Brain Products. A good reference for further amplifier settings. |

If the SDK is installed somewhere else, set the variable `AMPLIFIER_SDK` to that folder before you run the build script:
```bat
set "AMPLIFIER_SDK=D:\Tools\Amplifier SDK"
```

If you install a newer SDK version, also replace the `.dll` and `.bit` files in `Producer` with the ones from `Bin\x64` of that SDK, so that the program and its libraries match.

### Compiling the producer

You need Visual Studio 2019 or 2022. The free Community edition is enough. Select the workload **Desktop development with C++** during the installation. You also need the Amplifier SDK, see above.

1. Make sure the producer is not running.
2. Double-click `Producer/build.bat`, or run it in a terminal:
```bat
cd Producer
build.bat
```
The script finds Visual Studio and the SDK by itself and replaces `EEG_SharedMemoryProducer.exe`. To keep the old program, pass a different output folder, for example `build.bat C:\temp\producer`. Remember that the `.exe` only runs next to the `.dll` and `.bit` files.

You can also compile by hand. Open the **x64 Native Tools Command Prompt for VS** from the start menu and run:
```bat
cd Producer
set "SDK=C:\Vision\Amplifier SDK"
cl /EHsc /O2 /MT /I"%SDK%\Include" /I"%SDK%\Samples\C++" EEG_SharedMemoryProducer.cpp "%SDK%\Bin\x64\AmplifierSDK.lib" /Fe:EEG_SharedMemoryProducer.exe
```
It has to be the x64 prompt, because the SDK libraries are 64 bit.

To test the new producer on its own, start `EEG_SharedMemoryProducer.exe` in a terminal inside the `Producer` folder. It prints the memory layout, the number of amplifiers found and the applied sampling rate. Close it again before you use MATLAB or Python.

### Compiling the MEX functions

Each `.cpp` file in the `MATLAB` folder becomes one MEX function with the same name. The compiled `.mexw64` files are included, so you only need this step after a change.

1. Check that MATLAB has a C++ compiler: `mex -setup cpp`. Visual Studio and the MinGW-w64 add-on of MATLAB both work.
2. Open the `MATLAB` folder in MATLAB and run `compileMex.m`.

### If you change SharedBuffer.h

The producer, the MEX functions and the Python module must all use exactly the same memory layout. Otherwise they read wrong values without any error message. After every change of `SharedBuffer.h`:

1. Compile the producer again with `build.bat`.
2. Compile the MEX functions again with `compileMex.m`.
3. Apply the same change to the classes `ControlBlock` and `SharedBuffer` and to the constants `BUFFER_SIZE` and `MAX_CHANNELS` at the top of `Python/actiCHampConnect.py`.

The producer prints the size and the byte offsets of its structure at start. Use these numbers to check the Python side:
```python
import ctypes
from actiCHampConnect import SharedBuffer
print(ctypes.sizeof(SharedBuffer), SharedBuffer.impedances.offset, SharedBuffer.acquisitionReady.offset)
```

## Troubleshooting

| Problem | Likely cause and solution |
|---|---|
| "Producer exited" directly after connecting | The producer found no amplifier. Check USB cable, power and driver. Close BrainVision Recorder and other programs that use the amplifier. The producer output shows `Found 0 devices.` |
| "EEG_SharedMemoryProducer.exe is already running, closing it." | A previous run was not stopped. Connecting closes the old producer automatically (it is asked to stop and killed after `timeout` seconds). No action needed. |
| The producer window closes at once and a DLL is reported missing | The `.dll` and `.bit` files must be in the same folder as the `.exe`. A self-compiled producer may also need the Visual C++ Redistributable if it was not built with `/MT`. |
| MATLAB hangs in `ReadHybridMemory` | No samples arrive, for example because the producer crashed. The function cannot be interrupted, so MATLAB has to be ended in the Task Manager. End `EEG_SharedMemoryProducer.exe` there as well. |
| `GetImpedances` returns only -1 or an empty array | The first measurement takes a moment. If it stays like this, check the electrode connection and the reference and ground electrodes. |
| Data looks like noise or the columns are shifted | The memory layouts do not match. See [If you change SharedBuffer.h](#if-you-change-sharedbufferh). |
| `lost_samples()` is larger than zero | The reading side was too slow. Read more often or lower the sampling rate. |
| A MEX function cannot be compiled because the file is in use | Run `clear mex` in MATLAB and stop the producer. |

## Disclaimer

This is an independent project. It is not affiliated with, endorsed by, or supported by Brain Products GmbH. "actiCHamp" and "Brain Products" are trademarks of their respective owners. The software is provided as is, without warranty of any kind and without liability for any damages, and is not a medical device.

## License and third-party components

The source code written for this project is licensed under the Apache License 2.0, see [LICENSE](LICENSE). This covers the MATLAB and Python files, the MEX sources, `EEG_SharedMemoryProducer.cpp`, `SharedBuffer.h` and `build.bat`.

The producer uses the **BrainVision Amplifier SDK** of Brain Products GmbH. The following files in the `Producer` folder are unmodified compiled components of that SDK, version 1.1.0.2, Copyright (C) Brain Products GmbH:

- `AmplifierSDK.dll`
- `ActiChamp_x64.dll`
- `actiCHampLib.dll`
- `ActiChamp.bit`
- `ActiChampX.bit`

`EEG_SharedMemoryProducer.exe` is built with the headers, the import library and the sample file `RawDataHandlerExample.h` of the same SDK.

These components and the compiled producer are **not** covered by the Apache License. They are subject to the BrainVision Amplifier SDK Licensing Terms of Brain Products GmbH. In particular:

- They may be used for **non-commercial research purposes only**. Selling, renting, lending or leasing them, or software built on them, requires a written agreement with Brain Products.
- They must **not be used for high-risk or medically classified purposes** such as diagnosis or treatment.
- They are provided as is. All warranties and all liability for damages are excluded, as far as the law permits.
- The compiled components must not be modified, decompiled or reverse engineered.

The SDK itself is not part of this repository. Its headers, import library, documentation and samples must be downloaded from Brain Products, see [Getting the Amplifier SDK](#getting-the-amplifier-sdk). By using this project you agree to comply with the Brain Products licensing terms.
