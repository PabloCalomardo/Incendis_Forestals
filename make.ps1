param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]] $Args
)

$command = if ($Args.Count -gt 0) { $Args[0] } else { "dev" }
$rest = if ($Args.Count -gt 1) { $Args[1..($Args.Count - 1)] } else { @() }

if ($command -eq "install") {
  npm run install:all
  exit $LASTEXITCODE
}

npm run $command @rest
exit $LASTEXITCODE
