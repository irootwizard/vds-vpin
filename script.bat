@echo off
setlocal enabledelayedexpansion

if "%1"=="" (
    call :usage
    exit /b 1
)

set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

set DEFAULT_PORT_CNN_A=35000
set DEFAULT_PORT_CNN_B=35001
set DEFAULT_PORT_CNN_C=35002
set DEFAULT_PORT_CNN_D=35003
set DEFAULT_PORT_CNN_E=35004
set DEFAULT_PORT_LENET=35005
set DEFAULT_PORT_CONV=35006

set DEFAULT_BASE_PORT_CNN=36000
set DEFAULT_BASE_PORT_CONV=37000

set "LOG_DIR=%PROJECT_DIR%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set QUIET_MODE=1

rem Check for verbose flag in any argument position
if "%1"=="-v" set QUIET_MODE=0
if "%1"=="--verbose" set QUIET_MODE=0
if "%2"=="-v" set QUIET_MODE=0
if "%2"=="--verbose" set QUIET_MODE=0
if "%3"=="-v" set QUIET_MODE=0
if "%3"=="--verbose" set QUIET_MODE=0
if "%4"=="-v" set QUIET_MODE=0
if "%4"=="--verbose" set QUIET_MODE=0

rem Skip verbose flags when processing main command
if "%1"=="-v" (
    shift
    goto :check_cmd
)
if "%1"=="--verbose" (
    shift
    goto :check_cmd
)

:check_cmd
if "%1"=="-a" goto run_accuracy
if "%1"=="-c" goto run_cnn
if "%1"=="-l" goto run_lenet
if "%1"=="-b" goto run_baby_step
if "%1"=="-d" goto run_convolution
if "%1"=="" goto usage
goto usage

:usage
echo Usage: %~nx0 [-v] [-a ^| -c -A^-B^-C^-D^-E^-t ^| -l ^| -b ^| -d ^<3^|5^|7^> ^<32^|64^|128^|256^> ^| -d -t]
echo   -v, --verbose  Show verbose output from Server.py and Client.py in terminal
echo   -a       Check accuracy
echo   -c -A    Run CNN network A
echo   -c -B    Run CNN network B
echo   -c -C    Run CNN network C
echo   -c -D    Run CNN network D
echo   -c -E    Run CNN network E
echo   -c -t    Run all CNN networks sequentially
echo   -l       Run LeNet Model
echo   -b       Run baby-step-giant-step algorithm to precompute the table
echo   -d ^<3^|5^|7^> ^<32^|64^|128^|256^>  Run server and client with specified filter size and image size
echo   -d -t    Run all convolution experiments sequentially for all combinations of filter sizes (3,5,7) and image sizes (32,64,128,256)
exit /b 1

:run_accuracy
echo Running accuracy/train_test_lenet5.py...
python "%PROJECT_DIR%\src\accuracy\train_test_lenet5.py"
goto end

:run_cnn
rem Skip -v or --verbose if present
set CNN_ARG=%2
if "%2"=="-v" set CNN_ARG=%3
if "%2"=="--verbose" set CNN_ARG=%3
if "%3"=="-v" set CNN_ARG=%2
if "%3"=="--verbose" set CNN_ARG=%2

if "!CNN_ARG!"=="" (
    call :usage
    exit /b 1
)
if "!CNN_ARG!"=="-A" (
    call :run_server_and_client 1 %DEFAULT_PORT_CNN_A%
    goto end
)
if "!CNN_ARG!"=="-B" (
    call :run_server_and_client 2 %DEFAULT_PORT_CNN_B%
    goto end
)
if "!CNN_ARG!"=="-C" (
    call :run_server_and_client 3 %DEFAULT_PORT_CNN_C%
    goto end
)
if "!CNN_ARG!"=="-D" (
    call :run_server_and_client 4 %DEFAULT_PORT_CNN_D%
    goto end
)
if "!CNN_ARG!"=="-E" (
    call :run_server_and_client 5 %DEFAULT_PORT_CNN_E%
    goto end
)
if "!CNN_ARG!"=="-t" (
    call :run_all_experiments
    goto end
)
call :usage
exit /b 1

:run_lenet
call :run_server_and_client3 %DEFAULT_PORT_LENET%
goto end

:run_baby_step
echo Running baby-step-giant-step.py...
python "%PROJECT_DIR%\src\Pre_computed_table\baby-step-giant-step.py"
goto end

:run_convolution
rem Skip -v or --verbose if present
set CONV_ARG1=%2
set CONV_ARG2=%3
if "%2"=="-v" (
    set CONV_ARG1=%3
    set CONV_ARG2=%4
)
if "%2"=="--verbose" (
    set CONV_ARG1=%3
    set CONV_ARG2=%4
)
if "%3"=="-v" (
    set CONV_ARG2=%4
)
if "%3"=="--verbose" (
    set CONV_ARG2=%4
)
if "%4"=="-v" (
    set CONV_ARG2=%3
)
if "%4"=="--verbose" (
    set CONV_ARG2=%3
)

if "!CONV_ARG1!"=="-t" (
    call :run_all_convolution_experiments
    goto end
)
if "!CONV_ARG2!"=="" (
    call :usage
    exit /b 1
)
call :run_server_and_client2 !CONV_ARG1! !CONV_ARG2! %DEFAULT_PORT_CONV%
goto end

:run_server_and_client
setlocal
set version=%1
set port=%2

if "%version%"=="1" set network_label=A
if "%version%"=="2" set network_label=B
if "%version%"=="3" set network_label=C
if "%version%"=="4" set network_label=D
if "%version%"=="5" set network_label=E

for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /value') do set datetime=%%a
set datetime=%datetime:~0,8%-%datetime:~8,6%

set "logfile=%LOG_DIR%\%network_label%_Run_%datetime%.log"

echo Running server.py and client.py for CNN network %network_label% on port %port%...

if "%QUIET_MODE%"=="1" (
    netstat -an | findstr ":%port " >nul
    if !errorlevel! equ 0 (
        echo Alert: Port %port% is busy. Please select a different port.
    ) else (
        echo Port %port% is available.
    )
    echo Starting Server...
    set "server_log=%TEMP%\server_%port%_%random%.log"
    start /b python "%PROJECT_DIR%\src\cnn_networks\Server.py" "%version%" "%port%" >"%server_log%" 2>&1
    rem Wait for server to start listening on the port
    set /a retry_count=0
    :wait_for_server
    timeout /t 1 /nobreak >nul
    netstat -an | findstr /C:":%port%" | findstr /C:"LISTENING" >nul
    if !errorlevel! equ 0 (
        echo Server is ready.
        del "%server_log%" >nul 2>&1
        goto server_ready
    )
    rem Also check if port is in use (might be in ESTABLISHED or TIME_WAIT state)
    netstat -an | findstr /C:":%port%" >nul
    if !errorlevel! equ 0 (
        echo Server appears to be running on port %port%.
        del "%server_log%" >nul 2>&1
        goto server_ready
    )
    set /a retry_count+=1
    if !retry_count! geq 10 (
        echo Warning: Server may not have started properly.
        if exist "%server_log%" (
            echo Server error output:
            type "%server_log%"
            del "%server_log%" >nul 2>&1
        )
        echo Attempting to connect anyway...
        goto server_ready
    )
    goto wait_for_server
    :server_ready
    python "%PROJECT_DIR%\src\cnn_networks\Client.py" "%port%" >nul 2>&1
    echo Navigating to proof generation directory...
    cd /d "%PROJECT_DIR%\src\proof_generation\vPIN_proof_generation\src"
    echo Generating Proof...
    cargo run -- %network_label% >"%logfile%" 2>nul
    echo Proof generated, check logfile %network_label%_Run_%datetime%.log for seeing the result.
    echo.
) else (
    echo Starting Server...
    start /b python "%PROJECT_DIR%\src\cnn_networks\Server.py" "%version%" "%port%"
    rem Wait for server to start listening on the port
    set /a retry_count=0
    :wait_for_server_verbose
    timeout /t 1 /nobreak >nul
    netstat -an | findstr /C:":%port%" | findstr /C:"LISTENING" >nul
    if !errorlevel! equ 0 (
        echo Server is ready.
        goto server_ready_verbose
    )
    rem Also check if port is in use (might be in ESTABLISHED or TIME_WAIT state)
    netstat -an | findstr /C:":%port%" >nul
    if !errorlevel! equ 0 (
        echo Server appears to be running on port %port%.
        goto server_ready_verbose
    )
    set /a retry_count+=1
    if !retry_count! geq 10 (
        echo Warning: Server may not have started properly, attempting to connect anyway...
        goto server_ready_verbose
    )
    goto wait_for_server_verbose
    :server_ready_verbose
    python "%PROJECT_DIR%\src\cnn_networks\Client.py" "%port%"
    echo Navigating to proof generation directory...
    cd /d "%PROJECT_DIR%\src\proof_generation\vPIN_proof_generation\src"
    echo Generating Proof...
    cargo run -- %network_label% >"%logfile%" 2>&1
)
endlocal
goto :eof

:run_all_experiments
echo Running all CNN networks sequentially...
setlocal enabledelayedexpansion
for /l %%i in (1,1,5) do (
    set /a port=%DEFAULT_BASE_PORT_CNN% + %%i - 1
    call :run_server_and_client %%i !port!
)
endlocal
goto :eof

:run_server_and_client2
setlocal
set version=%1
set size=%2
set port=%3

if not "%version%"=="3" if not "%version%"=="5" if not "%version%"=="7" (
    echo Invalid version number: %version%. Allowed values are 3, 5, or 7.
    exit /b 1
)

if not "%size%"=="32" if not "%size%"=="64" if not "%size%"=="128" if not "%size%"=="256" (
    echo Invalid size: %size%. Allowed values are 32, 64, 128, or 256.
    exit /b 1
)

for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /value') do set datetime=%%a
set datetime=%datetime:~0,8%-%datetime:~8,6%

set "logfile=%LOG_DIR%\Convolution_%version%_%size%_Run_%datetime%.log"

echo Running server.py with filter size %version% and client.py with image size %size% on port %port%...

if "%QUIET_MODE%"=="1" (
    netstat -an | findstr ":%port " >nul
    if !errorlevel! equ 0 (
        echo Alert: Port %port% is busy. Please select a different port.
    ) else (
        echo Port %port% is available.
    )
    echo Starting Server...
    set "server_log=%TEMP%\server_%port%_%random%.log"
    start /b python "%PROJECT_DIR%\src\convolution\Server.py" "%version%" "%port%" "%size%" >"%server_log%" 2>&1
    rem Wait for server to start listening on the port
    set /a retry_count=0
    :wait_for_server_conv
    timeout /t 1 /nobreak >nul
    netstat -an | findstr /C:":%port%" | findstr /C:"LISTENING" >nul
    if !errorlevel! equ 0 (
        echo Server is ready.
        del "%server_log%" >nul 2>&1
        goto server_ready_conv
    )
    rem Also check if port is in use (might be in ESTABLISHED or TIME_WAIT state)
    netstat -an | findstr /C:":%port%" >nul
    if !errorlevel! equ 0 (
        echo Server appears to be running on port %port%.
        del "%server_log%" >nul 2>&1
        goto server_ready_conv
    )
    set /a retry_count+=1
    if !retry_count! geq 10 (
        echo Warning: Server may not have started properly.
        if exist "%server_log%" (
            echo Server error output:
            type "%server_log%"
            del "%server_log%" >nul 2>&1
        )
        echo Attempting to connect anyway...
        goto server_ready_conv
    )
    goto wait_for_server_conv
    :server_ready_conv
    python "%PROJECT_DIR%\src\convolution\Client.py" "%size%" "%port%" >nul 2>&1
    echo Navigating to proof generation directory...
    cd /d "%PROJECT_DIR%\src\proof_generation\vPIN_proof_generation\src"
    echo Generating Proof...
    cargo run -- "%version%_%size%" >"%logfile%" 2>nul
    echo Proof generated, check logfile Convolution_%version%_%size%_Run_%datetime%.log for seeing the result.
    echo.
) else (
    echo Starting Server...
    start /b python "%PROJECT_DIR%\src\convolution\Server.py" "%version%" "%port%" "%size%"
    rem Wait for server to start listening on the port
    set /a retry_count=0
    :wait_for_server_conv_verbose
    timeout /t 1 /nobreak >nul
    netstat -an | findstr /C:":%port%" | findstr /C:"LISTENING" >nul
    if !errorlevel! equ 0 (
        echo Server is ready.
        goto server_ready_conv_verbose
    )
    rem Also check if port is in use (might be in ESTABLISHED or TIME_WAIT state)
    netstat -an | findstr /C:":%port%" >nul
    if !errorlevel! equ 0 (
        echo Server appears to be running on port %port%.
        goto server_ready_conv_verbose
    )
    set /a retry_count+=1
    if !retry_count! geq 10 (
        echo Warning: Server may not have started properly, attempting to connect anyway...
        goto server_ready_conv_verbose
    )
    goto wait_for_server_conv_verbose
    :server_ready_conv_verbose
    python "%PROJECT_DIR%\src\convolution\Client.py" "%size%" "%port%"
    echo Navigating to proof generation directory...
    cd /d "%PROJECT_DIR%\src\proof_generation\vPIN_proof_generation\src"
    echo Generating Proof...
    cargo run -- "%version%_%size%" >"%logfile%" 2>&1
)
endlocal
goto :eof

:run_all_convolution_experiments
echo Running all convolution experiments sequentially...
setlocal enabledelayedexpansion
set index=0
for %%f in (3 5 7) do (
    for %%s in (32 64 128 256) do (
        set /a port=%DEFAULT_BASE_PORT_CONV% + !index!
        call :run_server_and_client2 %%f %%s !port!
        set /a index+=1
    )
)
endlocal
goto :eof

:run_server_and_client3
setlocal
set port=%1

echo Running LeNet Model (server.py and client.py) on port %port%...

if "%QUIET_MODE%"=="1" (
    netstat -an | findstr ":%port " >nul
    if !errorlevel! equ 0 (
        echo Alert: Port %port% is busy. Please select a different port.
    ) else (
        echo Port %port% is available.
    )
    echo Starting Server...
    set "server_log=%TEMP%\server_%port%_%random%.log"
    start /b python "%PROJECT_DIR%\src\LeNet\Server.py" "%port%" >"%server_log%" 2>&1
    rem Wait for server to start listening on the port
    set /a retry_count=0
    :wait_for_server_lenet
    timeout /t 1 /nobreak >nul
    netstat -an | findstr /C:":%port%" | findstr /C:"LISTENING" >nul
    if !errorlevel! equ 0 (
        echo Server is ready.
        del "%server_log%" >nul 2>&1
        goto server_ready_lenet
    )
    rem Also check if port is in use (might be in ESTABLISHED or TIME_WAIT state)
    netstat -an | findstr /C:":%port%" >nul
    if !errorlevel! equ 0 (
        echo Server appears to be running on port %port%.
        del "%server_log%" >nul 2>&1
        goto server_ready_lenet
    )
    set /a retry_count+=1
    if !retry_count! geq 10 (
        echo Warning: Server may not have started properly.
        if exist "%server_log%" (
            echo Server error output:
            type "%server_log%"
            del "%server_log%" >nul 2>&1
        )
        echo Attempting to connect anyway...
        goto server_ready_lenet
    )
    goto wait_for_server_lenet
    :server_ready_lenet
    python "%PROJECT_DIR%\src\LeNet\Client.py" "%port%" >nul 2>&1
    
    echo Navigating to proof generation directory...
    cd /d "%PROJECT_DIR%\src\proof_generation\vPIN_proof_generation\src"
    
    for /l %%i in (1,1,7) do (
        set layer=L%%i
        echo Generating Proof for !layer!...
        for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /value') do set datetime=%%a
        set datetime=!datetime:~0,8!-!datetime:~8,6!
        set "logfile=%LOG_DIR%\LeNet_!layer!_Run_!datetime!.log"
        cargo run -- !layer! >"!logfile!" 2>nul
        echo Proof generated, check logfile LeNet_!layer!_Run_!datetime!.log for seeing the result.
        echo.
    )
) else (
    echo Starting Server...
    start /b python "%PROJECT_DIR%\src\LeNet\Server.py" "%port%"
    rem Wait for server to start listening on the port
    set /a retry_count=0
    :wait_for_server_lenet_verbose
    timeout /t 1 /nobreak >nul
    netstat -an | findstr /C:":%port%" | findstr /C:"LISTENING" >nul
    if !errorlevel! equ 0 (
        echo Server is ready.
        goto server_ready_lenet_verbose
    )
    rem Also check if port is in use (might be in ESTABLISHED or TIME_WAIT state)
    netstat -an | findstr /C:":%port%" >nul
    if !errorlevel! equ 0 (
        echo Server appears to be running on port %port%.
        goto server_ready_lenet_verbose
    )
    set /a retry_count+=1
    if !retry_count! geq 10 (
        echo Warning: Server may not have started properly, attempting to connect anyway...
        goto server_ready_lenet_verbose
    )
    goto wait_for_server_lenet_verbose
    :server_ready_lenet_verbose
    python "%PROJECT_DIR%\src\LeNet\Client.py" "%port%"
    
    echo Navigating to proof generation directory...
    cd /d "%PROJECT_DIR%\src\proof_generation\vPIN_proof_generation\src"
    
    for /l %%i in (1,1,7) do (
        set layer=L%%i
        echo Generating Proof for !layer!...
        for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /value') do set datetime=%%a
        set datetime=!datetime:~0,8!-!datetime:~8,6!
        set "logfile=%LOG_DIR%\LeNet_!layer!_Run_!datetime!.log"
        cargo run -- !layer! >"!logfile!" 2>&1
    )
)
endlocal
goto :eof

:end
echo Script execution completed.
endlocal

