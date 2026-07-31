# SCQP Qblox measurement starter

這是一個從零開始、直接使用 `qblox-instruments` 的小型量測專案。它不使用 Qualibrate、QUAM 或 scqo。

目標樣品是 lambda-type superconducting qubit pair：

```text
QCM O1    -> 左側 flux line (Qa)
QCM O2    -> 右側 flux line (Qb)
QRM-RF O1 -> 上方 microwave transmission-line input
QRM-RF I1 <- 上方 microwave transmission-line output
QCM-RF II -> 額外 microwave tone，初期可不使用
```

照片推定 slot 2 是 QCM、slot 4 是 QCM-RF II、slot 6 是 QRM-RF；第一次一定要先用 `discover` 讀實機確認。

## 目前狀態

這些程式是可供後續 Codex 和實驗人員繼續完成的 **first-pass starter**：

- JSON validation、Q1ASM builder、CLI dry-run 與 Python 語法可在沒有 Qblox driver/硬體時測試。
- low-level hardware calls 依照 Qblox 2026 官方文件撰寫，但尚未在這一台 Cluster 上實際執行。
- 所有輸出 script 預設 dry-run；必須明確加入 `--execute` 才會連線並啟用輸出。
- 真實 sample connectors、attenuation、device power limit 未填以前，sample measurement 會拒絕執行。
- `Cluster.reset()` 預設被禁止；它會重置整個機箱，不是只重置一個 sequencer。

## 使用現有 Qblox 環境

2026-07-31 已確認桌面根目錄的既有環境：

```text
C:\Users\USER\Desktop\qblox\.venv-qblox
Python 3.12.13
qblox-instruments 1.3.0
QCoDeS 0.56.0
```

必要的 NumPy、matplotlib、xarray、h5netcdf、pytest 也都已安裝。將本小專案 editable install 到該環境：

```powershell
cd C:\Users\USER\Desktop\qblox\SCQPMeasurement
..\.venv-qblox\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item hardware_config.example.json hardware_config.json
```

不要把 Qblox 套件安裝到 QM 專案的 `.venv`。

安裝後先記錄版本：

```powershell
..\.venv-qblox\Scripts\python.exe -m pip show qblox-instruments qcodes
qblox-pnp list
```

同時核對 Cluster firmware 與 driver compatibility。Qblox 曾撤回 firmware 0.12.0，因 acquisition 可能過早回報完成；應使用相容且已修正的版本。

## 執行順序

### 0. 純軟體測試

```powershell
..\.venv-qblox\Scripts\python.exe -m pytest -q
..\.venv-qblox\Scripts\python.exe -m experiments.qcm_scope --config hardware_config.json
..\.venv-qblox\Scripts\python.exe -m experiments.qrm_rf_loopback --config hardware_config.json
```

上面沒有 `--execute`，不會連線或輸出。

### 1. 唯讀連線

先把 `hardware_config.json` 的 Cluster IP/hostname 填好：

```powershell
..\.venv-qblox\Scripts\python.exe -m experiments.discover --config hardware_config.json
```

確認：

- slot 2 確實是 `is_qcm_type=True, is_rf_type=False`
- slot 4 確實是 `is_qcm_type=True, is_rf_type=True`
- slot 6 確實是 `is_qrm_type=True, is_rf_type=True`
- system status 沒有 error flag
- firmware 與 `qblox-instruments` 相容

`discover` 不 reset、不 arm、不 start、不開 LO。

### 2. QCM 示波器測試

不要先接 cryostat：

```text
QCM O1 -> 適當衰減/50 ohm termination -> scope
```

先 dry-run，再人工確認接線後：

```powershell
..\.venv-qblox\Scripts\python.exe -m experiments.qcm_scope --config hardware_config.json --side left
..\.venv-qblox\Scripts\python.exe -m experiments.qcm_scope --config hardware_config.json --side left --execute
```

右側改成 `--side right`。預設 waveform amplitude 只有 0.002，但仍須依示波器、線路與衰減重新確認。

### 3. QCM-RF II 測試

```text
QCM-RF II O1 -> RF attenuator -> spectrum analyzer / sufficient-bandwidth RF scope
```

```powershell
..\.venv-qblox\Scripts\python.exe -m experiments.qcm_rf_scope --config hardware_config.json
..\.venv-qblox\Scripts\python.exe -m experiments.qcm_rf_scope --config hardware_config.json --execute
```

不要因一般示波器看不到 GHz carrier 就提高功率。

### 4. QRM-RF loopback

```text
QRM-RF O1 -> 至少 30 dB、頻帶與功率合格的固定衰減器 -> QRM-RF I1
```

填入 `microwave_chain.loopback_fixed_attenuation_db` 後：

```powershell
..\.venv-qblox\Scripts\python.exe -m experiments.qrm_rf_loopback --config hardware_config.json --execute
```

程式保存 scope path0/path1。QRM-RF raw scope 位於 digital demodulation 前，會看到 IF；真正的 sweep 使用 binned integrated I/Q。

### 5. SCQP microwave transmission

先確認並填入：

- `sample.microwave_input_connector`
- `sample.microwave_output_connector`
- `microwave_chain.source_to_sample_attenuation_db`
- `microwave_chain.sample_to_adc_gain_db`
- `microwave_chain.max_device_input_dbm`

然後才可執行：

```powershell
..\.venv-qblox\Scripts\python.exe -m experiments.microwave_spectroscopy `
  --config hardware_config.json --start-hz 5e9 --stop-hz 7e9 --points 201 --execute
```

輸出是未經 VNA calibration 的 relative complex S21：I、Q、amplitude、phase。

### 6. 左右 flux spectroscopy

一次只掃一條 flux：

```powershell
..\.venv-qblox\Scripts\python.exe -m experiments.flux_spectroscopy `
  --config hardware_config.json --side left --flux-start-v -0.002 `
  --flux-stop-v 0.002 --flux-points 21 --probe-points 101 --execute
```

必須先校正可接受的 command-voltage 範圍、ramp rate、bias tee，以及 QCM 與外部 DC source 是否會互相灌電流。尚未校正 `volts_per_phi0` 前，資料只標示 command voltage，不能標成 flux quantum。

### 7. Parametric spectroscopy

在 static-flux sweep 找到 degeneracy、bright-state frequency 及 `2J` 後：

```powershell
..\.venv-qblox\Scripts\python.exe -m experiments.parametric_spectroscopy `
  --config hardware_config.json --side left --probe-hz 6.2e9 `
  --pump-start-hz 50e6 --pump-stop-hz 300e6 --pump-points 101
```

確認 dry-run/Q1ASM 後才加入 `--execute`。程式以 pump OFF/ON 成對量測並保存 delta I/Q/amplitude；它量到的是 transmission response，未經模型驗證不能直接稱為 qubit population。

## 重要頻帶限制

```text
QCM       : DC/baseband，約 0-400 MHz
缺口      : 約 400 MHz-2 GHz
QCM-RF II : 2-18.5 GHz，AC coupled
QRM-RF    : 2-18.5 GHz
```

理論的 parametric resonance 約為 `f_phi = f_B - f_D = 2J`。論文示例是 1.4 GHz，剛好在現有模組缺口，但那不是本樣品的已知值。先從 avoided crossing 量出實際 `2J`；若落在缺口，需外部 RF source/mixer，與 Cluster 共用 10 MHz reference 並由 marker trigger。也必須確認 bias tee、低溫濾波器、flux line 和封裝能通過該頻率。

## Script 清單

| Command | 狀態 | 功能 |
|---|---|---|
| `experiments.discover` | 可先執行 | 唯讀連線與 inventory |
| `experiments.qcm_scope` | scope 驗證後 | QCM finite baseband pulse |
| `experiments.qcm_rf_scope` | RF 儀器驗證後 | QCM-RF II finite burst |
| `experiments.qrm_rf_loopback` | 固定衰減器驗證後 | RF output + scope/bin acquisition |
| `experiments.microwave_spectroscopy` | loopback 通過後 | relative S21(f) |
| `experiments.flux_spectroscopy` | flux chain 校正後 | relative S21(flux, f) |
| `experiments.parametric_spectroscopy` | 找到 degeneracy/2J 後 | pump OFF/ON response |

## 官方參考

- [Qblox Instruments Tutorial 0](https://docs.qblox.com/en/main/applications/setupguides/any/setupqbloxinstruments.html)
- [QCM basic sequencing](https://docs.qblox.com/en/main/products/qblox_instruments/tutorials/QCM/010_basic_sequencing.html)
- [QCM-RF II](https://docs.qblox.com/en/main/products/architecture/modules/qcm_rf.html)
- [QRM-RF scope acquisition](https://docs.qblox.com/en/main/products/qblox_instruments/tutorials/QRM-RF/030_scope_acquisition.html)
- [QRM-RF architecture and limits](https://docs.qblox.com/en/main/products/architecture/modules/qrm_rf.html)
- [Q1ASM](https://docs.qblox.com/en/main/products/qblox_instruments/q1/index.html)
