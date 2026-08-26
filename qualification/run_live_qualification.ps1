param (
    [Parameter(Mandatory=$false)]
    [string]$Mode = "contract",

    [Parameter(Mandatory=$true)]
    [string]$Scenario,

    [Parameter(Mandatory=$false)]
    [int]$Repeat = 1
)

python qualification/run_live_qualification.py --mode $Mode --scenario $Scenario --repeat $Repeat
