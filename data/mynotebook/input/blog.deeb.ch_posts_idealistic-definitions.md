# https://blog.deeb.ch/posts/idealistic-definitions/

# An Idealistic View of Malware Analysis Definitions

Or: WTF is heuristics?

![Idealistic Definitions](https://blog.deeb.ch/definitions/static-dynamic-analysis.png)

Most people are confused about what heuristics is, or whats the difference between static- and dynamic analysis.
Lets try to define it.

## Static Analysis

Static analysis only operates on the file itself. It will not be executed.

The analyzer will typically open the file content, and interpret the bytes in its format. For .exe it would be PE (Portable Executable) format. It will parse the file to inspect the sections, imports, header information, and the stored data and code.

This is safe (no potentially malicious code is executed) and fast (basically IO and CPU speed bound).

## Dynamic Analysis

Dynamic analysis involves execution of the file. This can either be:

- Separate execution in an internal emulator
- Separate execution in a secure sandbox (local, or cloud)
- Observe execution on the host itself (typically EDR on endpoints)

During execution, two different artefacts can be investigated:

- What the process contains (data)
- What the process is doing (actions)

The first, what the process contains, is again very similar to static analysis. Just that it happens on memory instead of a file on disk. This can be called a memory scan.

Actions are specific to dynamic analysis. Only when executing it, it is possible to see
what its doing.

## Heuristic

Heuristics means “looks malicious” (but aint sure).

> They use “heuristics” that humans evolved for making snap decisions but that can mislead them at other times.
> From [thesaurus.com](https://www.thesaurus.com/browse/heuristic), Wall Street Journal

It can be used with a points system: Each heuristic detection gives +x points, and if an exe accumulates more than y points, it is considered malicious.

Alternatively, heuristics can pinpoint areas to further investigate, like if the entropy of certain file sections dont match expectations.

Heuristics often dont look at just the specific bytes in the file, but “are centered around indirectly derived hashes, patterns, and header traits” (mgeeky).

## Determinstic

The opposite of heuristic I call here “deterministic”.
Deterministic means “is malicious”. It is a detection which is precise. A string of bytes, or behaviour, which is known malicious.

Note: “Deterministic” is only being used for the sake of the discussion in this article, as the opposite of “heuristic”. It is not used in the security scene. Typically we use “signature-based” instead, which i show here it wrong, as signatures can also be heuristic.

Typically a good example for a deterministic (or even “signature-based”) detection is a yara rule which matches for unique bytes of a certain malware.
And, even more so, the MD5/SHA256 hash of a file which is known malicious, like the releases of mimikatz.exe on github.

## On Heuristics vs. Deterministic Signatures

Signatures are usually precise: They specify which bytes the target has to contain so that the rule is triggered.

An example of [PWS:Win32/Frethog.AB](https://defendersearch.r00ted.ch/threat?name=PWS%3AWin32%2FFrethog.AB):

```
rule PWS_Win32_Frethog_AB_2147597356_0
{
    meta:
        author = "defender2yara"
        detection_name = "PWS:Win32/Frethog.AB"
        threat_id = "2147597356"
        type = "PWS"
        platform = "Win32: Windows 32-bit platform"
        family = "Frethog"
        severity = "Critical"
        signature_type = "SIGNATURE_TYPE_PEHSTR_EXT"
        threshold = "52"
        strings_accuracy = "High"
    strings:
        $x_10_1 = "CreateToolhelp32Snapshot" ascii //weight: 10
        $x_10_2 = "08E909A4-48DD-8BCC-B236-90A604B93E68" ascii //weight: 10
        $x_10_3 = "RavMon.exe" ascii //weight: 10
        $x_10_4 = "AVP.AlertDialog" ascii //weight: 10
        $x_10_5 = "#32770" ascii //weight: 10
        $x_1_6 = "Forthgoer" ascii //weight: 1
        $x_1_7 = "tldoor%d.dll" ascii //weight: 1
        $x_1_8 = "FilMsg.exe" ascii //weight: 1
        $x_1_9 = "Twister.exe" ascii //weight: 1
    condition:
        (filesize < 20MB) and
        (
            ((5 of ($x_10_*) and 2 of ($x_1_*))) or
            (all of ($x*))
        )
}
```

These signatures can be either precise (deterministic), or heuristic (more generic).

Lets say all Mimikatz executables contain the string `Mimikatz_OpenInternalConfig()` from the source code. A signature which alerts on exe files which contain the string `Mimikatz_OpenInternalConfig()` is deterministic: There is basically no false positives, if its found in a (.exe PE) file its most likely Mimikatz.

But there can also be signatures which are more generic. A yara rule which looks for the string `LSASS` inside a exe is more a heuristic: The file is not 100% malicious. Even though the signature is precise, the interpretation is not.

## On Heuristic vs. Deterministic

The difference between those two is blurry, and different people or systems have a different view.

For RedTeamer, opening the LSASS process looks very suspicious, and a clear indicator of malicious behaviour. But for a sysadmin, this may be completely normal, as many processes are doing this for whatever reason.

Similarly, a process opening another process to inject and run code again looks very suspicious and malicious. But this is a completely normal behaviour for many windows programs: For copy protection, DRM, gathering crash information, telemetry, hot-patching etc.

## Static analysis discussion

Static analysis is typically considered what “Anti Virus” software is doing. Viruses (as in self-replicating file infectors) dont really exist anymore since 25+ years, so Antivirus AV usually means static analysis of files.

The antivirus can also look at the file imports, and consider certain imports, or combinations thereof, malicious. Like an import for “OpenProcess()” and “LsaRetrievePrivateData()”. This is more heuristics.

The standard virus-definition in the DB, where unique strings of each virus is stored and matched against files, is static anlysis and deterministic. The signatures are usually automatically generated for known malware specimens (and with it, families).

## Dynamic analysis discussion

Dynamic analysis also enables to observe what the process is doing: Behaviour analysis. Either via hooking ntdll, or consuming the ETW events generated by process.

For example, if there is a rule which detects if a process opens a handle to lsass, its more heuristic. A surprisingly large amount of programs are doing that. Its not yet clear if its indeed malicious.

If there is a rule which detects if a process reads sensitive information of the lsass process, as used in mimikatz, the rule is more like deterministic. Thats a pretty good indicator of a malicious program.

## Emulators

Are emulators static analysis? The code is not really executed, its just the AV reading the content of the file, which is more static analysis. Is it dynamic analysis? The code is executed, but not on the CPU, and not with the real system (but just in a emulator).

It can be one or the other, or even both together. For this article, i put it into the “dynamic analysis” category. Some people call it “static emulation”.

Emulator are typically employed during/with static analysis. But the results are more similar to dynamic analysis.

## Conclusion

The difference between static- and dynamic analysis should be mostly clear, as its a simple difference.

Heuristics also has a simple definition, but is harder to apply. It often depends on context,
and can have different meaning depending on the abstraction layer you are at.