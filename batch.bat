@ECHO OFF

@SET M3_BIN_NAME=opl1000_app_at_m3.bin
@SET M0_BIN_NAME=RW_IRAM1.bin
@SET BASE_DIR=%~dp0..\..\
@SET CURRENT_DIR=%CD%
@SET ROM_M3_DIR=APS\targets\opl1000\Output\Objects
@SET ROM_M0_DIR=MSQ\targets\opl1000\Output\Objects\opl1000_patch_m0.bin

@echo %~dp0

@REM Copy bin to dw_batch folder
@COPY %BASE_DIR%%ROM_M3_DIR%\%M3_BIN_NAME% %~dp0
@COPY %BASE_DIR%%ROM_M0_DIR%\*.bin %~dp0

@REM Combine M3 and M0 BIN files and download to device
@IF NOT EXIST %~dp0\%M3_BIN_NAME% ( GOTO DONE )
@IF NOT EXIST %~dp0\%M0_BIN_NAME% ( GOTO DONE )
@CD %~dp0
@START download.py -b %M3_BIN_NAME%

@REM Delete M3 and M0 bin files
::@DEL %~dp0%M3_BIN_NAME%
::@DEL %~dp0\*.bin

:DONE 