# https://blog.deeb.ch/posts/maldev-myths/

# MalDev Myths

For years I have seen techniques used in MalDev that have been obsolete
for some time now or just applied wrongly. A short list.

When doing MalDev, you have to consider against what you want
to protect your code:

- Automated systems which will detect and block your malware
- Manual reverse engineering of the functionality of your malware

I focus on the first, as I want a working beacon. If the SOC reverses
my malware, I buy them beer.
This article is RedTeaming specific and about loaders and droppers.
Storing malicious code in files or memory.

Automated detection mostly means AntiVirus (AV), EDR, and stuff
like sandboxes. This article doesn’t consider the use case for
manual reverse engineering.

This list is based on Sektor7’s courses (maldev essentials, intermediate, and Windows evasion).
But I see this kind of obsolete information everywhere - as if the hacker scene didn’t catch up to
current developments, and just blindly rehashes stuff from the 90s.
Even worse is that all MalDev courses and trainings I’ve seen just randomly throw techniques together and hope for the best. Instead of analyzing security software first, and finding blind spots. For example by trying to [understand how EDRs work](https://blog.deeb.ch/posts/how-edr-works/) first.

This information is not based on experience but on understanding computer fundamentals, Windows basics, and security products.

## Where to store payloads

If you want to store data in an exe, for example for a dropper, there are
several places to choose from, including:

- .text
- .data
- .rsrc

Which one should you take? It doesn’t really matter.

![PE sections](https://blog.deeb.ch/malwaremyths/pe-sections.png)

![PE sections2](https://blog.deeb.ch/malwaremyths/pe-sections2.png)

If you modify an existing .exe, both `.text` and `.data` don’t really
have enough free space (only maybe a few 100 bytes). If you add a lot
of data in it, you gonna trash it, making the program unable to run
correctly. `.rsrc` often has lots of available space.

If you generate the .exe by yourself, it doesn’t matter. EDR’s don’t really
see where data is coming from when copying it around. It’s inside the process space from one memory location to another, which can’t really be seen -
the EDR isn’t able to distinguish it.

Software doing static analysis of the file may influence your decision a little bit.

**Conclusion**:

- Stop to care about where to put your data.
- Just put code into `.text`, and data into `.data` or `.rsrc`. Look normal.
- When backdooring exes, use `.rsrc` or other sections where overwriting data doesn’t matter
- Just _don’t_ create new PE sections, that stand out.

## Entropy

If you encrypt or compress stuff and put it into a .exe, it will have
higher entropy than the surrounding data. This can be detected, and will
result in an event like:

> Higher entropy found in .text section between 0x1234 and 0x5432.

Here a graphical example:

![PE entropy](https://blog.deeb.ch/malwaremyths/pe-entropy2.png)

This is not a reliable detection. Security software blocking executables
with high entropy at unexpected places will block many genuine executables. The above
screenshot is from the tool DIE-engine, analyzing DIE-engine itself.

Discussing entropy is cool - but it’s not that relevant for automated analysis.

**Conclusion**:

- Entropy can help manual reverse engineering but is rarely a reliable automated indicator.
- If you are scared of entropy analysis, just base64 your data
- Generally try to blend in, by encoding your stuff similar to surrounding data

## How to encrypt/encode the payload for storage

In many shellcode loaders, there are several implementations of different encryption/encoding
methods implemented. Like XOR, RC4, AES, Hex-Encoding, or similar
(see [1](https://github.com/r00tkie/CipherCraft) [2](https://github.com/Ne0nd0g/go-shellcode) [3](https://github.com/D3Ext/Hooka)
).

Which one you choose doesn’t matter. A EDR or AV cannot magically crack encryption -
it doesn’t have a quantum computer inside. It doesn’t even know which encryption algorithm
you implemented - hell it doesn’t even know that you encrypt or decrypt something.
It cannot trace all the instructions, and recover the original intent from it.
An exception is using standard Windows API to encrypt, like AES or Base64 from crypt32.dll .
Or when using a standard encryption library with well-known signatures.
See [Shellcode Obfsucation Lab](https://github.com/dobin/ShellcodeObfuscationLab) for a detailed analysis.

Static analysis software which have enough time (async, e.g. virustotal) can attempt
to try all the standard decodings like base64 or XOR with all 255 single byte keys on all (?),
data, like in global variables.

**Conclusion**:

- Encrypt your stuff however you want, it doesn’t matter much
- Avoid using Windows API’s to do it tho
- The data will be securely encrypted in the file on disk - and decrypted in memory on usage (memory scanners!)
- Try to avoid 1-byte XOR, as it results in a potential pattern - use at least 2-byte XOR
- If your data is very easily discernable, avoid standard methods (base64, single byte XOR etc.) or prepend a random character

## Function call obfuscation / IAT heuristics

The .exe has a list of all used/imported DLL functions in the IAT (import address table).
Some security software has a look at this to decide if the software looks malicious
or not. If your output is “may be malicious”, then it’s [heuristics](https://en.wikipedia.org/wiki/Heuristic_analysis).

It’s not reliable, by definition, and as most Windows software does a lot of crazy things,
and imports the typical malicious-looking functions.

See for example the imports from the tool cffexplorer.exe of itself. Is this malicious or not?

![PE imports](https://blog.deeb.ch/malwaremyths/pe-imports.png)

Analyze putty, process monitor, or any other tool to see how abnormal their IAT looks.

**Conclusion**:

- Don’t use/import _exclusively_ potentially malicious functions - try to look normal.
- Try to make it look normal (good API stuffing, or backdooring existing executables).
- If scared, use `GetModuleHandle()` and `GetProcAddres()` \- these are very commonly used anyway by genuine programs, but can be an IOC
- Alternatively, implement `GetModuleHandle()` & `GetProcAddress` yourself with a PEB walk. But: Existing PEB walk implementations ou copy may be signatures

## Signed EXE / Certificate

What happens if you (correctly) sign an executable? Will it not be scanned by the AV?
Will it be whitelisted by the EDR? I don’t know, but I doubt it.
This is heavily security tool dependent.

Leaked code signing certs are commonly available - expired, revoked, or not.
Will signing your malware with such a cert improve detection, or make it more obvious?
Can security software really depend on it, when we have leaked certs - and DLL sideloading?
What about self-signed certificates, are they useful at all?

I think some security vendors want to make their lives easy, and for performance- and false-positive reasons will skip signed executables. Reasonable security software would just mostly ignore it.

**Conclusion**:

- Sign it and try. I usually don’t.

## Code/Process injection

Want to inject code into another process? Dont.

There are typically three steps involved:

- Access the target process (`OpenProcess()`)
- Allocate and write memory in remote process (`VirtualAllocEx()`, `WriteProcessMemory()`)
- Execution primitive (`CreateRemoteThread()`)

EDR will depend on seeing variants of these three things for detection.
Cross-process stuff is well scrutinized by the EDR.

**Conclusion**:

- If you want to do process injection, skip at least one of the three primitives
- As a starter, don’t do `CreateRemoteThread()` \- find another way
- Prefer DLL sideloading

## “EDR Bypass” / ntdll unhooking

Some EDR’s hook `ntdll.dll` instead of using ETW. Only bad ones. Many good
EDR’s don’t use this technique anymore. Including MDE, Elastic, Cortex.

ntdll hooking is obsolete. It always was, and always will be, bypassable
with direct- or indirect syscalls, or ntdll recovering or re-patching.
The EDR can also just check if their hooks got removed - it blows my
mind this is not standard. Direct- or indirect syscalls can be reliably
detected with ETW and callstack analysis, and are a big IOC.
The public implementations for in/direct syscalls are also often signatured.

If you _have_ to use ntdll syscalls, include callstack spoofing.

**Conclusion**:

- If you work against an obsolete fun EDR which does ntdll hooking, do some non-signatured direct- or indirect syscalls implementation with callstack spoofing

## ETW Patching

ETW is the Event Tracing for Windows, its like Syslog, or Windows Event Logs.
A process can create ETW events by itself: e.g. for performance monitoring,
or application-specific events. The Windows kernel will also generate ETW
events, based on what a process is doing.

It’s not possible to disable ETW, unless you are in the Kernel.
You can only stop the application-specific events by patching
ETW in the process - which aren’t that important. Most of the ETW
events are not created by the process itself.

```
 Process                     OS                     EDR
┌─────────────┐ EtwWrite() ┌──────────┐          ┌──────────────┐
│             ├───────────►│          │          │              │
│             │            │ ────────►│          │              │
│             │            │          │   ETW    │              │
│             │            │          ├─────────►│              │
│             │            │          │          │              │
│             │ syscalls   │ ────────►│          │              │
│             ├───────────►│          │          └──────────────┘
│             │            │          │
│             │            └──────────┘
│             │
│             │
└─────────────┘
```

The main confusion comes from the fact that there are “two ETW”:
One can be influenced and patched away - the other, with the important
data, cannot. Also, AMSI and Defender themselves create many ETW
events about what they are doing, which may add to the confusion.

**Conclusion**:

- Just don’t. Unless you can 100% prove it’s useful
- Unless you want to patch AMSI to load .NET or Powershell code.

## VirusTotal 2/99

VirusTotal is mostly static analysis. Which means it scans the file
for known signatures. It does not really do a lot of runtime
analysis (executing the file), like with a Sandbox or EDR.

VirusTotal can be trivially bypassed by:

- Encrypting your shellcode
- Decrypt it without signatured code
- Add some execution guardrails

Conclusion:

- If you publish a x/y VT result to prove “FUD”, I know it’s gonna be bad

## Unusual C2 Channels

A beacon usually communicates with the C2 server relay via HTTP GET and POST
messages.

Some people use other services:

- Google Docs, Sheets
- Twitter, Xing, Linkedin
- Pastebin
- Slack, Discord, Teams
- Azure Cloud Services
- ETH Smart Contracts via Web API

So instead of sending HTTP requests to X, we send it to Y (with a few correct headers).
There is nothing technically impressive about this. These techniques often generate a lot of
media coverage, if the service being used is new, cool or uncool
(think Teams, Blockchain, LLMs).

This can surely help blend in the C2 traffic for an attentive SOC - but that’s
very rare. More useful is to bypass domain whitelisting, which is even rarer.

Conclusion:

- Just Update the standard C2 HTTP template (malleable) if there’s detection for the default HTTP requests

# Examples

Random examples of loaders I encounter.

## Pwntricks

In the blog [Bypass Cortexxdr And Sophos Edr Like Real Red Teamer](https://www.pwntricks.com/Bypass-CortexXDR-and-Sophos-EDR-like-real-red-teamer):

- Patching ETW: ETW is not really used here, bad
- Decrypt with AES: using Windows functions, bad
- Unhook ntdll: Cortex doesn’t do hooking. Sophos does. Still bad
- Module Stomping: Good
- Local thread hijacking: Good
- Custom Havoc C2 profile: Good
- Sandbox bypass with file bloating: Good

The first three techniques are obsolete and most likely not needed, and only increase the detection rate. The last four techniques are good and useful and do the actual bypass work.

## Hunter

[https://github.com/S3N4T0R-0X0/Hunter](https://github.com/S3N4T0R-0X0/Hunter)

- API Unhooking: Not important
- Syscall Dispatcher: Together with API unhooking, not important
- ETW Nullification: Not important or helpful
- Process termination methods: Irrelevant
- Anti-Analysis: Simple, irrelevant
- Sandbox Detection: Good!

The only useful part of this project is the Sandbox Detection.
The rest increases the detection rate more than reducing it.

## Outsmarting Windows Defender

[https://blog.rian-friedt.de/windows-evasion-techniques-outsmarting-windows-defender/](https://blog.rian-friedt.de/windows-evasion-techniques-outsmarting-windows-defender/)

- Static Evasion:
  - Strip identifying metadata from payloads: Good
  - Modify open-source crypters to evade detection: Good
  - Use PowerShell reflection to bypass AMSI: Good
- Dynamic Evasion:
  - Spoof parent-child process relationships: Ok, but can be an IOC
  - Unhook APIs and use direct syscalls: Bad, not relevant for Defender
  - Abuse trusted system binaries (LOLBAS): Good

The training seems to use Powershell/DotNet loaders, which is good (hide behind JIT).
Will block AMSI so the managed code is not being scanned.
Identify the signatured loader/amsi-patch code and change it.
A reasonable and sane approach.

## Erebus

[https://github.com/RePRGM/Erebus/tree/main](https://github.com/RePRGM/Erebus/tree/main)

- ETW patching: Bad. Doesnt help, as payload is not in a managed language
- NTDLL unhooking: Situational
- Custom GetProcAddress implementation: Questionable. Does it really help?
- Sandbox checking: Good
- Encryption with UUID, RCE, AES etc: Bad. Just use XOR

Using NIM can be a IOC though.

# Rustloadloader

[https://blog.shellntel.com/p/evading-microsoft-defender](https://blog.shellntel.com/p/evading-microsoft-defender)

- Use Rust: Irrelevant
- Use LUA: Good
- Use XOR: Good
- Use virustotal: Bad

Seems to Rust-only version got caught by the Defender AV emulator.
The Lua-Rust did not.

# How to do it correctly

My proposed shellcode loader architecture:

```
 ┌──────────┐
 │ encrypted│
 │ Payload  │
 └────┬─────┘
      │
      │
      ▼
┌──────┐    ┌────────────┐    ┌───────────┐    ┌─────────────┐   ┌──────────┐   ┌────────────┐
│ EXE  │    │ Execution  │    │ Anti      │    │EDR          │   │ Alloc RW │   │  Payload   │
│ File ├───►│ Guardrails ├───►│ Emulation ├───►│deconditioner├──►│ Decode/Cp├──►│  Execution │
│      │    │            │    │           │    │             │   │ RX       │   │            │
│      │    │            │    │           │    │             │   │ Exec     │   │            │
└──────┘    └────────────┘    └───────────┘    └─────────────┘   └──────────┘   └────────────┘
```

## Execution Guardrails

Check first if you are on the intended target. For example by checking the ENV variables,
if the host is in the correct AD.

This will prohibit middleboxes from executing your code: VirusTotal, Proxy AV, Sandboxes etc.
It will only be executed on the target, with its AV and EDR.

## Anti Emulation

Many AV will emulate the binary. The AV will interpret the instructions, and scan
its memory for known signatures. Your encrypted will be exposed with this.

Emulation will have a cutoff, and stop analysis after X amount of time,
or Y amount of instructions executed. So at the start of your loader, do
a few 100'000 instructions.

Doing manual decryption of the shellcode may already fulfill the cutoff.
This is where the myth of “more encryption means less detection” comes from.

## EDR deconditioner

To execute your decrypted shellcode, need to:

1. Allocate memory RW
2. Copy shellcode
3. Change memory permissions to RX
4. Execute the shellcode

EDR deconditioning does number 1-3, many times, with non-malicious fake data, making the EDR tired of scanning our shit. Then later, do 1-4.

## Executing the shellcode

Execute the shellcode as normal as possible. Just jump to the shellcode (`jmp`).

Do not use execution primitives like `CreateThread()`. Or, only if you know its not well known (e.g. with a Windows function callbacks).

## Putting it together

Do the things I mention above first.

If it still gets detected, the fun begins. Try to think about how the stuff
gets detected, and try to bypass it. When you find a solution, take a step
back and try to think about why it worked - if your assumption was correct.
Or if it’s just not being detected anymore for completely unrelated reasons.

For more information, see:

- [SuperMega Shellcode Loader](https://blog.deeb.ch/posts/supermega/)
- [Cordyceps Injection Technique](https://blog.deeb.ch/posts/exe-injection/)
- [Anti EDR Compendium](https://blog.deeb.ch/posts/how-edr-works/)
- Slides [My First and Last Shellcode Loader](https://docs.google.com/presentation/d/1BtLtsh0pBrF6XwlyGHoxBnuIAKtgJM4jwNSxTFRu1yo/edit?usp=sharing)

# MalDev Course examples

## Sektor7

Malware Dev Essentials:

- PE Intro
- Droppers
    \\* Where to store payloads
- Obfuscating and hiding
    \\* Shellcode encryption
    \\* Call obfuscation
- Backdoors and trojans
    \\* Backdooring PE
- Code injection
    \\* Injecting code into remote processes
    \\* Loading DLLs into remote processes