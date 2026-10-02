# Windows release preparation

```powershell
.\prepare-release-windows.ps1 -Tag v0.6.5 -DryRun
.\prepare-release-windows.ps1 -Tag v0.6.5
```

The helper checks clean `main` at `origin/main`, runs pytest and core coverage,
then invokes the existing PyInstaller builder and validates the Windows ZIP.
The macOS app, DMG, signing, and notarization gates remain on macOS.
