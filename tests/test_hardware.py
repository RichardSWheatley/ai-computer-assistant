from rita.hardware import GPU, Hardware, recommend_model


def test_no_vram_recommends_cloud():
    hw = Hardware(gpus=[])
    assert hw.has_vram is False
    assert hw.acceleration == "cpu"
    rec = recommend_model(hw)
    assert rec["lean_on_claude"] is True


def test_cuda_gpu_detected():
    hw = Hardware(gpus=[GPU(name="RTX 4090", vram_mb=24564, backend="cuda")])
    assert hw.has_vram is True
    assert hw.acceleration == "cuda"
    assert hw.total_vram_mb == 24564
    rec = recommend_model(hw)
    assert rec["tier"] == "sweet-spot"
    assert rec["lean_on_claude"] is False


def test_metal_backend():
    hw = Hardware(gpus=[GPU(name="Apple", vram_mb=65536, backend="metal")])
    assert hw.acceleration == "metal"


def test_detect_hardware_runs():
    # Should never raise, even with no GPU and no optional deps.
    from rita.hardware import detect_hardware
    hw = detect_hardware()
    assert isinstance(hw.gpus, list)
