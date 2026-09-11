# Windows public-trust signing

The preview backend is blocked by Smart App Control (WinError 4551). The existing package is unsigned. A self-signed certificate is not a substitute for public-trust publisher verification.

Microsoft Artifact Signing (formerly Trusted Signing) requires an Azure subscription, a signing account, completed publisher identity validation, and a **Public Trust** certificate profile. The signing identity needs the Certificate Profile Signer role. Account provisioning can incur charges; complete the billing and identity steps in your own account. Do not send passwords, private keys, or identity documents to the development chat.

Official setup: https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart

Official client/authentication instructions: https://learn.microsoft.com/en-us/azure/artifact-signing/how-to-signing-integrations

Install the official Artifact Signing Client Tools (includes the signing plugin and prerequisites), and authenticate using a supported credential such as an Azure CLI login. Use x64 SignTool with the x64 Azure.CodeSigning.Dlib.dll. This machine already has Windows SDK SignTool 10.0.26100.0.

Create a metadata JSON outside the package with the actual account values (these are identifiers, not secrets):

```json
{
  "Endpoint": "https://YOUR_REGION.codesigning.azure.net",
  "CodeSigningAccountName": "YOUR_ACCOUNT",
  "CertificateProfileName": "YOUR_PUBLIC_TRUST_PROFILE"
}
```

Use the exact endpoint shown for your account. After building, inspect the existing bundle without changing it:

```powershell
.\worker\windows\sign-package.ps1 -AppDirectory '.\dist\windows-discovery\extracted\DynoWorker' -InventoryOnly
```

Once the signing account is ready:

```powershell
.\worker\windows\sign-package.ps1 `
  -AppDirectory '.\dist\windows-discovery\extracted\DynoWorker' `
  -OutputDirectory '.\dist\windows-signed' `
  -MetadataPath 'C:\path\to\metadata.json' `
  -DlibPath 'C:\path\to\x64\Azure.CodeSigning.Dlib.dll'
```

The output directory must not exist. The script verifies the original runtime manifest, copies the bundle, preserves valid vendor signatures, signs unsigned EXE/DLL/PYD/PowerShell files with SHA-256 and an RFC 3161 timestamp, verifies signatures, and regenerates runtime hashes after signing. Invalid existing signatures stop packaging. Failures preserve the original package and leave an incomplete staging directory for investigation, without producing a ZIP. A successful run writes a separate signed ZIP, checksum and per-file signing report.

Signature verification alone does not prove that every Windows policy permits execution. Final acceptance must launch the signed GUI, start/stop the GPU backend, exercise elevated setup, and check CodeIntegrity events on this host with its protections enabled. Then test one-to-one pairing and inference.
