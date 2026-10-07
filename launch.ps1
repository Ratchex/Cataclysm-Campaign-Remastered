# Launch HWRM with this mod loaded from loose files (via the DataCataclysm junction) and HW1 campaign data,
# so Kushan/Taiidan single-player scripts are available. The campaign is under Single Player > Extra Missions.
# One-time setup (junction):
#   cmd /c mklink /J "<HomeworldRM>\DataCataclysm" "C:\Modding\Cataclysm-HWRM\data"
$bin = "C:\Program Files (x86)\Steam\steamapps\common\Homeworld\HomeworldRM\Bin\Release"
Start-Process -FilePath "$bin\HomeworldRM.exe" -WorkingDirectory $bin -ArgumentList @(
    '-dlccampaign', 'HW1Campaign.big', '-moviepath', 'DataHW1Campaign',
    '-moddatapath', 'DataCataclysm', '-overrideBigFile', '-luatrace') -PassThru
# Log: <HomeworldRM>\Bin\Release\HwRM.log (contains NUL bytes; strip them before grepping)
