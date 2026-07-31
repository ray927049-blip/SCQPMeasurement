# Qblox SCQP 連線與最小量測系統規劃

## 0. 已確認的樣品與硬體拓撲

本計畫針對使用者的 lambda-type superconducting qubit pair（SCQP），不是 resonator-based qubit readout，也不使用 Qualibrate 或 scqo。

樣品線路已由使用者確認：

```text
左側 flux line   -> Qa 的獨立 static flux / parametric modulation
右側 flux line   -> Qb 的獨立 static flux / parametric modulation
上方 microwave transmission line -> 共同耦合 Qa、Qb，作為 probe 與 S21 readout
```

由機箱照片初步辨識（仍必須由 discovery script 讀取實機確認）：

```text
slot 0 : CMM
slot 2 : QCM
slot 4 : QCM-RF II
slot 6 : QRM-RF
```

建議角色：

```text
QCM O1       -> 左 flux line (Qa)
QCM O2       -> 右 flux line (Qb)
QRM-RF O1    -> 上方 microwave transmission-line input
QRM-RF I1    <- 上方 microwave transmission-line output
QCM-RF II O1 -> 保留給獨立 microwave tone / two-tone spectroscopy
```

若 sample box 的 microwave line 不是 two-port，QRM-RF O1/I1 中間必須加入 circulator 或 directional coupler，改量 S11；在 connector mapping 確認前不得接樣品執行。

## 1. 目標

這份文件是交給後續 Codex 與實驗人員使用的工作規格。第一階段不做完整的量子實驗，先確認以下最小閉環：

1. 電腦能透過 Ethernet 連線至 Qblox Cluster。
2. Python 能辨識 Cluster 內 slot 2 QCM、slot 4 QCM-RF II 與 slot 6 QRM-RF。
3. QCM 能輸出低振幅測試波形，並在示波器上看見。
4. QCM-RF II 能輸出低功率 RF burst，並由合適頻寬的示波器或頻譜分析儀看見。
5. QRM-RF 能輸出測試波形；完成外部 loopback 後，能把 acquisition 資料讀回 Python。
6. 每次測試都會在 `data/` 下保存參數、硬體設定快照、狀態、原始資料與圖片。
7. 能量測 microwave transmission 的相對 complex S21：I、Q、amplitude、phase。
8. 能分別設定左右 static flux，找到兩個 qubit 的 degeneracy 與 bright-state feature。
9. 能同步執行 QCM flux parametric drive 與 QRM-RF microwave probe/acquisition。

第一階段成功後，再把重複程式整理成簡單的 experiment API，最後才增加參數頁面。

## 2. 安全界線（第一次接線前必讀）

- 不要在尚未確認接線、終端阻抗和儀器輸入限制時開啟輸出。
- 示波器輸入設為 **50 Ω**；若示波器只允許 1 MΩ，使用外接 50 Ω terminator。
- QCM baseband 輸出先經過適當的外部衰減器，再接示波器。
- QCM-RF II 的輸出只能接到支援該 RF 頻率與功率的示波器、頻譜分析儀或接收路徑。一般低頻示波器可能看不到載波。
- RF 測試一開始使用最大的合理 output attenuation、短 burst 和低 AWG amplitude，再逐步提高訊號。
- QRM-RF loopback 前，必須核對 input 的最大允許功率；第一次測試在 output 與 input 之間至少使用經確認的 30 dB 固定衰減器。
- 第一次 bring-up 不連接 qubit、resonator、放大器或 cryostat RF chain，只接測試儀器或安全的 loopback cable。
- 不把密碼或 token 寫進 JSON。Cluster IP/hostname 可以寫入設定檔。
- 程式必須用 `try/finally`：即使中途失敗，也要停止 sequencer、關閉 RF LO/輸出，最後關閉 QCoDeS instrument。
- `reset()` 會改變模組目前狀態；共享儀器上執行前，要確認沒有其他使用者正在量測。
- QCM static offset 範圍雖可達伏特等級，SCQP flux line 第一次測試只能使用經現場 attenuation / mutual inductance 換算後的低安全值；程式另設較小的 software safety limit。
- QRM-RF 的量測值在完成 cable/background calibration 前只能稱為 relative S21，不宣稱是校正後的絕對 S-parameter。

### 必須處理的頻帶缺口

```text
QCM       : 約 0-400 MHz（flux modulation）
缺口      : 400 MHz-2 GHz
QCM-RF II : 2-18.5 GHz
QRM-RF    : 2-18.5 GHz
```

理論上的 parametric resonance 是 `f_phi ~= f_B - f_D = 2J`。論文示例為 1.4 GHz，但樣品實際值尚未量得。如果實際 `2J` 落在 400 MHz-2 GHz，現有模組不能直接產生該 flux tone，需使用外部 RF generator / mixer 或其他涵蓋此頻帶的硬體。程式必須拒絕不在所選 source 頻帶內的設定。

> 實際電壓、頻率及功率限制以現場型號、韌體版本、datasheet 和示波器規格為準，不要只依賴本文件中的示意值。

## 3. 建議的專案結構

```text
hardware_configs/
└── qblox_cluster.example.json     # 可提交的範例，不含實驗室私密資訊

scqp_qblox/
├── __init__.py
├── config.py                      # JSON 載入、schema 驗證
├── hardware.py                    # Cluster 連線、型號檢查、安全關閉
├── sequences.py                   # Q1ASM 與 waveform builders
├── acquisition.py                 # QRM-RF scope/bin acquisition
└── data.py                        # run folder、JSON/CSV/NetCDF/figure

experiments/
├── discover.py                    # 唯讀：列出 Cluster 與 modules
├── qcm_scope.py                   # QCM -> oscilloscope
├── qcm_rf_scope.py                # QCM-RF II -> RF scope/spectrum analyzer
├── qrm_rf_loopback.py             # QRM-RF O1 -> attenuator -> I1
├── microwave_spectroscopy.py      # relative S21(f_probe)
├── flux_spectroscopy.py           # relative S21(f_probe, flux)
└── parametric_spectroscopy.py     # relative S21(f_probe, f_phi, A_phi)

data/
└── qblox_bringup/<timestamp>/
    ├── parameters.json
    ├── hardware_snapshot.json
    ├── instrument_status.json
    ├── raw_data.nc                # 有 acquisition 時
    ├── raw_data.csv               # 方便人工查看
    └── figure.png
```

Qblox 程式放在獨立的 `Desktop\qblox` 專案，不改動目前 QM 的 `customized/scqo/`，也不註冊 scqo backend。

## 4. Hardware config JSON 草案

建議先建立 `hardware_configs/qblox_cluster.example.json`：

```json
{
  "schema_version": 1,
  "cluster": {
    "name": "cluster0",
    "address": "REPLACE_WITH_CLUSTER_IP_OR_HOSTNAME"
  },
  "modules": {
    "qcm": {
      "slot": 2,
      "expected_type": "QCM",
      "left_flux_output": 0,
      "right_flux_output": 1,
      "parametric_sequencer": 0
    },
    "qcm_rf": {
      "slot": 4,
      "expected_type": "QCM-RF II",
      "sequencer": 0,
      "output": 0,
      "lo_frequency_hz": 5000000000,
      "nco_frequency_hz": 10000000,
      "output_attenuation_db": 60
    },
    "qrm_rf": {
      "slot": 6,
      "expected_type": "QRM-RF",
      "sequencer": 0,
      "output": 0,
      "input": 0,
      "lo_frequency_hz": 5950000000,
      "nco_frequency_hz": 50000000,
      "output_attenuation_db": 30,
      "input_attenuation_db": 30
    }
  },
  "sample": {
    "microwave_topology": "transmission",
    "left_flux_source": "qcm.out0",
    "right_flux_source": "qcm.out1",
    "microwave_source": "qrm_rf.out0",
    "microwave_detector": "qrm_rf.in0"
  },
  "safety": {
    "max_abs_static_flux_voltage_v": 0.01,
    "max_flux_waveform_amplitude": 0.05,
    "max_qcm_parametric_frequency_hz": 400000000,
    "min_rf_frequency_hz": 2000000000,
    "max_rf_frequency_hz": 18500000000,
    "require_execute_flag": true
  },
  "bringup_defaults": {
    "waveform_length_ns": 100,
    "waveform_amplitude": 0.05,
    "repeat_count": 1000,
    "repeat_period_ns": 10000
  }
}
```

注意：slot 2/4/6 是根據照片的初步判讀，IP、port mapping、LO frequency、attenuation 與 static flux limit 仍是占位值，不能直接拿去控制現場硬體。程式在執行前必須比較 `expected_type` 與實際 module type，不一致就中止，不能猜測。

Hardware config 只描述連線與安全預設值。掃頻起點、終點、平均次數等量測參數，應放在 experiment parameters，不要混進硬體 mapping。

## 5. 實作順序與驗收條件

### Milestone A：建立環境與唯讀連線

工作內容：

- 建立獨立的 Qblox Python 環境；本專案說明中預期使用 `.venv-qblox`。
- 安裝並記錄 `qblox-instruments`、QCoDeS、NumPy、SciPy、xarray、matplotlib 的確切版本。
- 用 Qblox Plug & Play discovery 或已知 IP/hostname 找到 Cluster。
- 連線後列出 Cluster identity、firmware/software build、所有 populated slots 與 module type。
- 驗證 JSON 中每個 slot 的 `expected_type`。
- 此階段不 reset、不 arm、不 start，也不開啟 RF LO。

驗收：

- 終端機清楚列出 QCM、QCM-RF II、QRM-RF 的 slot 與型號。
- IP 錯誤、slot 空白或型號不符時，程式以非零 exit code 結束並給出可讀錯誤。
- `finally` 中正確關閉 instrument，重跑不會遇到重複的 QCoDeS instrument name。

預計命令介面：

```powershell
python -m customized.qblox.bringup.discover --config hardware_configs/qblox_cluster.json
```

### Milestone B：QCM baseband 示波器測試（第一個真正輸出）

接線：

```text
QCM O1 ── external attenuator ── oscilloscope CH1 (50 Ω)
QCM marker 1（可選）──────────── oscilloscope EXT TRIG/CH2
```

測試波形：100 ns、低 amplitude 的 Gaussian，每 10 µs 重複一次；marker 包住 pulse，方便示波器 trigger。第一次應先用有限次數，不要無限 loop。

最小 sequence 內容包括 waveform dictionary、空 weights/acquisitions 與 Q1ASM。Q1ASM 概念如下，實際語法需按已安裝的 `qblox-instruments` 版本及官方 tutorial 實作：

```text
wait_sync 4
move repeat_count,R0
loop:
  set_mrk 1
  play 0,1,4
  set_mrk 0
  wait remaining_period
  loop R0,@loop
stop
```

Codex 實作時應遵循官方基本流程：建立 waveforms/weights/acquisitions/program、上傳 `sequence`、設定 channel map、arm、start、讀取 sequencer status、停止及關閉。

驗收：

- 示波器可穩定 trigger。
- CH1 看見約 100 ns 的 Gaussian envelope，週期約 10 µs。
- sequencer 最終狀態為正常停止，沒有 error flags。
- 改變 JSON 中的 amplitude 或 period 後，示波器結果相應改變。

### Milestone C：QCM-RF II burst 測試

接線：

```text
QCM-RF II O1 ── RF attenuator ── RF oscilloscope / spectrum analyzer (50 Ω)
```

先確認觀測儀器頻寬涵蓋 `LO + NCO`。建議輸出短 Gaussian 或 square envelope，採用最大合理的模組 output attenuation 與很低的 waveform amplitude。設定 LO/NCO 後，要依 RF 模組規則正確控制 output switch/marker。

驗收：

- 頻譜中心出現在預期的 `LO ± NCO`；正負號以實際 mixer/channel 設定確認。
- RF burst 長度和重複週期符合設定。
- 改變 NCO frequency 後，觀測到的頻率位移一致。
- 執行完畢或發生例外後，RF LO/output 回到安全關閉狀態。

如果只有低頻示波器，先跳過此項；不能因為看不到波形就提高功率。

### Milestone D：QRM-RF output 與 acquisition loopback

先做 QRM-RF output 到合適的 RF 儀器。確認 output 正常後才做 loopback：

```text
QRM-RF O1 ── fixed attenuator ── QRM-RF I1
```

QRM-RF sequence 同時包含 `play` 與 `acquire`。程式需要：

- 配置 output channel map 與 acquisition input map。
- 宣告至少一個 acquisition，例如 `single`。
- arm/start 後等待 acquisition 完成，必須有 timeout。
- store scope acquisition，再取得 acquisitions。
- 將 path0/path1 資料轉成 xarray/CSV 並畫圖。

驗收：

- Python 取得非空的 scope acquisition。
- 圖中 pulse 的位置與寬度符合 sequence。
- 重跑時會先清除舊 acquisition，資料不會混到前一次結果。
- timeout、overrange、sequencer error 都會被保存到 status JSON 並使程式失敗。

### Milestone E：SCQP microwave transmission spectroscopy

接線確認為 two-port 後：

```text
QRM-RF O1 -> cryostat input -> 上方 microwave line -> cryostat output -> QRM-RF I1
```

先量 cable/background，再量 sample relative S21。每個 probe frequency 保存平均後的 I/Q，並計算：

```text
amplitude = sqrt(I^2 + Q^2)
phase = atan2(Q, I)
```

掃描得到 `I(f_probe)`、`Q(f_probe)`、`|S21|` 與 unwrapped phase。未做 VNA-style calibration 前不輸出絕對 dB S21。

### Milestone F：左右 static-flux spectroscopy

分別掃 QCM O1/O2 的 static offset，目標是辨識兩個 bare-qubit branches、avoided crossing、degeneracy point 與 bright-state frequency。每次掃描必須從安全小範圍開始，結束或例外時將兩個 offset 恢復為 config 的 safe idle values。

輸出資料至少包含：

```text
I(left_flux, right_flux, probe_frequency)
Q(left_flux, right_flux, probe_frequency)
amplitude / phase
```

第一版只允許一次掃一條 flux，另一條固定；完整二維 flux-flux-frequency 掃描留到背景與熱負載確認後。

### Milestone G：parametric spectroscopy

QCM 對左或右其中一條 flux line 施加 sinusoidal modulation；QRM-RF 同步發出弱 microwave probe 並 acquisition：

```text
QCM:    parametric flux tone，f_phi ~= f_B - f_D
QRM-RF: probe near |G> <-> |B>
```

先做 pump OFF / ON 成對量測並保存 `delta_I`、`delta_Q`、`delta_amplitude`、`delta_phase`。第一版掃 `f_phi`，第二版才加入 parametric amplitude 與 pulse duration。找到 response 後再考慮 EIT/ATS fit、bright-dark swapping 與 STIRAP。

### Milestone H：統一 CLI 與資料保存

前三項通過後才進行：

- 抽出共用的 config loader、connection context manager、safe shutdown、status checker。
- 為 JSON 建立 schema/Pydantic 驗證及純軟體 unit tests。
- 每次執行自動建立唯一的 timestamp/UUID data directory。
- 保存「實際使用的」參數和 hardware config snapshot，而不只是原始輸入檔。
- 使用獨立的 `.venv` 與 `pyproject.toml`；不依賴本專案的 QM/QUAM/Qualibrate/scqo。
- 最後才建立頁面；頁面與 CLI 必須呼叫同一個 Python experiment API。

## 6. 建議先完成的最小 script

第一支應實作 `discover.py`，第二支才是 `qcm_scope.py`。`qcm_scope.py` 的責任限制如下：

```python
def run_qcm_scope(config_path: str, *, dry_run: bool = False) -> Path:
    """驗證設定、連線、輸出有限次低振幅 Gaussian、保存狀態並安全關閉。"""
```

必要行為：

1. 讀 JSON 並驗證欄位。
2. 顯示即將使用的 Cluster、slot、port、amplitude、pulse length 和 repeat count。
3. `--dry-run` 只能驗證並列印，不得 reset/arm/start。
4. 連線後再次核對 module type。
5. 載入 sequence，檢查 sequencer status，再 arm/start。
6. 等待有限序列結束並設定 timeout。
7. 保存 status 與設定快照。
8. `finally` 執行 safe shutdown 和 close。

不應做的事：

- 不自動掃描並選擇「第一台」Cluster 後直接輸出。
- 不在型號不符時嘗試其他 slot。
- 不使用無限 waveform loop 作為第一個測試。
- 不在程式碼內硬編碼現場 IP、slot 或 RF power。
- 不把硬體測試放進一般 `pytest`，避免測試套件意外啟動輸出。

## 7. 測試策略

### 不需要硬體的測試

- JSON schema 正確/缺欄位/錯誤型別。
- module type 不符時拒絕執行。
- amplitude、attenuation、frequency、repeat count 越界時拒絕執行。
- Q1ASM/sequence builder 產出所需的四個區段。
- mocked Cluster 發生連線、上傳或 start 例外時，仍呼叫 safe shutdown 與 close。
- data directory 與 metadata 能正確建立。

### 需要硬體、必須人工明確啟動的測試

- `discover` 唯讀連線。
- QCM scope output。
- QCM-RF II RF output。
- QRM-RF scope output。
- QRM-RF acquisition loopback。

硬體測試應使用獨立命令或 `pytest -m hardware` 且預設跳過；不能隨一般 unit test 自動執行。

## 8. 給後續 Codex 的執行提示

把下面這段作為後續工作的起始要求：

> 請先完整閱讀 `QBLOX_BRINGUP_PLAN.md` 與獨立 qblox 專案的 `README.md`。這是左右 flux、上方 microwave transmission line 的 SCQP，不是 resonator readout，也不使用 scqo/Qualibrate。先檢查本機 Qblox venv、`qblox-instruments` 版本、Cluster IP、slot/module inventory、sample-box connector mapping、attenuation 與示波器規格。先提出 plan，再取得使用者同意後修改程式。第一步只執行 dry-run 與唯讀 `discover.py`；不得 reset 或啟動輸出。所有實際輸出必須明確加入 `--execute`，預設有限次、低 amplitude，並具有 timeout、status 檢查、safe shutdown。

進入 QCM 實際測試前，Codex 必須向使用者取得以下現場資料：

- Cluster IP/hostname。
- 各 module 的真實 slot 與完整型號（QCM/QCM-RF II/QRM-RF）。
- Qblox firmware 與 `qblox-instruments` 版本。
- 使用哪個實體 output/input connector。
- 示波器頻寬、最大輸入、50 Ω 支援狀況。
- 外部 attenuator 值與額定頻寬/功率。
- RF 測試預計使用的安全 LO frequency。

## 9. 官方參考資料

- [Qblox Instruments Tutorial 0：QCM、QRM、QRM-RF 輸出與 acquisition](https://docs.qblox.com/en/main/applications/setupguides/any/setupqbloxinstruments.html)
- [Basic sequencing：連線、sequence JSON、arm/start 與示波器 marker](https://docs.qblox.com/en/main/products/qblox_instruments/tutorials/QRM/010_basic_sequencing.html)
- [Q1 Sequencer 架構與 Q1ASM](https://docs.qblox.com/en/main/products/architecture/sequencers/sequencer.html)
- [QCM 架構與輸出](https://docs.qblox.com/en/main/products/architecture/modules/qcm.html)
- [QCM-RF II：LO、attenuation、output switch 與頻帶](https://docs.qblox.com/en/main/products/architecture/modules/qcm_rf.html)
- [QRM-RF 架構、channel mapping、input/output limits](https://docs.qblox.com/en/main/products/architecture/modules/qrm_rf.html)
- [QRM-RF scope acquisition](https://docs.qblox.com/en/main/products/qblox_instruments/tutorials/QRM-RF/030_scope_acquisition.html)

官方文件會隨 `qblox-instruments` 版本更新。實作時要優先閱讀與本機套件版本相符的文件或下載 notebook，不要直接複製舊版 Pulsar API 範例。

## 10. 完成定義

第一階段只有在以下項目全部成立時才算完成：

- [ ] 已保存實際 Cluster identity、版本與 module inventory。
- [ ] QCM Gaussian 可在示波器穩定觀察，並保存 sequencer status。
- [ ] QCM-RF II burst 可在合適的 RF 儀器觀察，結束後安全關閉。
- [ ] QRM-RF loopback 能取得 scope acquisition 並保存 raw data 與 figure。
- [ ] 已確認上方 microwave line 的兩個 sample-box connectors，完成 relative S21 frequency sweep。
- [ ] 已用左右 static flux sweep 找到 qubit branches、degeneracy 與 bright-state feature。
- [ ] 已量得或限制 `f_B-f_D=2J`，並確認 parametric source 頻帶可用。
- [ ] Pump OFF/ON parametric spectroscopy 能保存 delta I/Q/amplitude/phase。
- [ ] 所有 script 支援 `--config` 與 `--dry-run`，並有 timeout。
- [ ] 任一例外都會執行 safe shutdown。
- [ ] 一般 unit tests 不會接觸或啟動硬體。
- [ ] 現場使用者能只修改 JSON/experiment parameters，不必改 Python 連線程式。
