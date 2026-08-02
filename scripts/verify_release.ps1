$ErrorActionPreference = "Stop"

python -m pytest -q --cov=aprendix --cov-branch
if ($LASTEXITCODE -ne 0) {
    throw "Release verification tests failed."
}

python -m compileall -q src mobile tests
if ($LASTEXITCODE -ne 0) {
    throw "Bytecode compilation failed."
}

$unsafe = rg -n "(TODO|FIXME|NotImplementedError)" src mobile tests
if ($LASTEXITCODE -eq 0) {
    $unsafe
    throw "Placeholder or unsafe execution marker detected."
}
if ($LASTEXITCODE -ne 1) {
    throw "Source scan failed."
}

# The excluded grading/sandbox modules are dedicated child-process boundaries;
# every other application module must remain free of dynamic execution.
$hostExecution = rg -n "(^|[^_])(eval\(|exec\()" src mobile `
    -g "*.py" `
    -g "!python_sandbox.py" `
    -g "!**/python_sandbox.py" `
    -g "!grading.py" `
    -g "!**/grading.py" `
    -g "!mobile/aprendix_mobile/execution.py"
if ($LASTEXITCODE -eq 0) {
    $hostExecution
    throw "Unsafe host-process execution marker detected."
}
if ($LASTEXITCODE -ne 1) {
    throw "Host execution scan failed."
}

Write-Output "Release verification complete."
