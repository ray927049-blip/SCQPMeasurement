# Windows 快速開始

## 第一次一鍵安裝

在 PowerShell 執行以下單一命令，即可安裝並在目前視窗啟用環境：

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force; . .\setup.ps1 -Activate
```

若只想安裝、不啟用，則可在 PowerShell 或命令提示字元執行：

```powershell
cd C:\Users\user\Desktop\SCQPMeasurement
.\setup.cmd
```

這會依照 `.python-version` 與 `pyproject.toml`：

1. 由 `uv` 尋找或安裝 Python 3.12。
2. 自動建立或更新 `.venv`。
3. 安裝專案、Qblox、科學運算及 dev/test 套件。
4. 確認 Python 版本並執行全部測試。

`pyproject.toml` 是套件與版本宣告，無法自行執行；實際的一鍵入口是 `setup.cmd`。

## 啟用既有環境

專案目前的虛擬環境是 Python 3.12.10。在 PowerShell 執行：

```powershell
cd C:\Users\user\Desktop\SCQPMeasurement
.\.venv\Scripts\Activate.ps1
python --version
```

若目前 PowerShell 禁止執行啟用腳本：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

也可以完全不啟用，直接使用 `.\.venv\Scripts\python.exe` 執行以下命令。

## 離線 dummy 測量

這個命令模擬 qubit-resonator dispersive readout 的 power-frequency sweep，不會匯入 Qblox driver、不會開啟網路連線，也不需要 `--execute`：

```powershell
python -m experiments.dummy_measurement --config hardware_config.json
```

自訂測試範圍：

```powershell
python -m experiments.dummy_measurement `
  --config hardware_config.json `
  --resonance-hz 6e9 --start-hz 5.99e9 --stop-hz 6.01e9 --points 301 `
  --chi-hz 2e6 --linewidth-hz 1.5e6 `
  --power-start-dbm -70 --power-stop-dbm -20 --power-points 51 `
  --critical-power-dbm -35 --seed 42
```

模型令 qubit 在 `|g>` 和 `|e>` 時的低功率 resonator 頻率分別為 `fr-chi` 與 `fr+chi`，因此兩條 resonance 的間距是 `2*chi`；超過 critical power 後，有效 dispersive shift 會逐漸縮小。

結果會存入 `data\日期\dummy_dispersive_power_時間戳\`，包含：

- `dummy_dispersive_power.csv`
- `dummy_dispersive_power.nc`
- `dummy_dispersive_power.png`
- `hardware_config_snapshot.json`
- `parameters.json`
- `instrument_status.json`

## 自動測試

```powershell
python -m pytest -q
```

## 連接真實 Qblox

在 `hardware_config.json` 設定 Cluster 管理介面的 IP 或 hostname：

```json
"cluster": {
  "name": "scqp_cluster",
  "address": "192.168.0.2",
  "reference_clock": "internal"
}
```

確認 `modules.qcm.slot`、`modules.qcm_rf.slot` 和 `modules.qrm_rf.slot` 符合實際安裝位置後，執行唯讀探索：

```powershell
python -m experiments.discover --config hardware_config.json
```

dummy 成功只代表 Python、參數檢查、數值資料與存檔流程可用，不代表真實 Qblox 的網路、firmware、模組、接線或 RF/flux 安全設定已驗證。
