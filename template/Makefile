TOP ?= top
DEVICE ?= hx1k
PACKAGE ?= vq100
PCF ?= constraints.pcf
BUILD ?= build

.PHONY: all clean

all: $(BUILD)/$(TOP).bin

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/$(TOP).json: src/$(TOP).v | $(BUILD)
	yosys -p "read_verilog src/$(TOP).v; synth_ice40 -top $(TOP) -json $@"

$(BUILD)/$(TOP).asc: $(BUILD)/$(TOP).json $(PCF)
	nextpnr-ice40 --$(DEVICE) --package $(PACKAGE) --pcf $(PCF) --json $< --asc $@

$(BUILD)/$(TOP).bin: $(BUILD)/$(TOP).asc
	icepack $< $@

clean:
	rm -rf $(BUILD)
