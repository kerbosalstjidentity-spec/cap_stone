# fds-research 데이터셋·작업 Make 타겟 (W5.5-#2)
#
# 사용:
#   make paysim-download     # PaySim CSV 다운로드 (Kaggle API 키 필요)
#   make paysim-stats        # 다운로드된 CSV 의 분포 검증

PYTHON ?= python
DATA_DIR := data
PAYSIM_CSV := $(DATA_DIR)/paysim.csv

.PHONY: paysim-download paysim-stats paysim-clean

paysim-download: $(PAYSIM_CSV)

$(PAYSIM_CSV):
	@mkdir -p $(DATA_DIR)
	@echo "[paysim] downloading ealaxi/paysim1 via Kaggle API..."
	@command -v kaggle >/dev/null 2>&1 || (echo "ERROR: kaggle CLI 미설치. 'pip install kaggle' 후 ~/.kaggle/kaggle.json 배치." && exit 1)
	kaggle datasets download -d ealaxi/paysim1 -p $(DATA_DIR) --unzip
	@if [ -f "$(DATA_DIR)/PS_20174392719_1491204439457_log.csv" ]; then \
		mv "$(DATA_DIR)/PS_20174392719_1491204439457_log.csv" "$(PAYSIM_CSV)"; \
	fi
	@echo "[paysim] saved to $(PAYSIM_CSV)"

paysim-stats:
	@$(PYTHON) -m scripts.paysim.load

paysim-clean:
	rm -f $(PAYSIM_CSV)
