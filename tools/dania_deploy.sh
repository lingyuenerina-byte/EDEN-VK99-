#!/usr/bin/env bash
set -e
cd /i/dania-tts/gsv

echo "== 1. pretrained base weights (hf-mirror) =="
mkdir -p GPT_SoVITS/pretrained_models/chinese-hubert-base \
         GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large \
         GPT_SoVITS/pretrained_models/v2Pro
M="https://hf-mirror.com/lj1995/GPT-SoVITS/resolve/main"
dl(){ curl -sL -m 900 --retry 3 -o "$2" "$M/$1" && echo "  ok $2"; }
dl "chinese-hubert-base/config.json"            GPT_SoVITS/pretrained_models/chinese-hubert-base/config.json
dl "chinese-hubert-base/preprocessor_config.json" GPT_SoVITS/pretrained_models/chinese-hubert-base/preprocessor_config.json
dl "chinese-hubert-base/pytorch_model.bin"      GPT_SoVITS/pretrained_models/chinese-hubert-base/pytorch_model.bin
dl "chinese-roberta-wwm-ext-large/config.json"  GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large/config.json
dl "chinese-roberta-wwm-ext-large/vocab.txt"    GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large/vocab.txt
dl "chinese-roberta-wwm-ext-large/pytorch_model.bin" GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large/pytorch_model.bin
dl "s1v3.ckpt"                                  GPT_SoVITS/pretrained_models/s1v3.ckpt
dl "v2Pro/s2Gv2ProPlus.pth"                     GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth

echo "== 2. dania finetuned weights in place =="
mkdir -p GPT_weights_v2ProPlus SoVITS_weights_v2ProPlus output/slicer_opt
cp -f ../model/dania-e15.ckpt        GPT_SoVITS/dania-e15.ckpt
cp -f ../model/dania_e16_s2192.pth   GPT_SoVITS/dania_e16_s2192.pth
cp -f ../model/tts_infer.yaml        GPT_SoVITS/configs/tts_infer.yaml
cp -f ../model/dania-e15.ckpt        GPT_weights_v2ProPlus/dania-e15.ckpt
cp -f ../model/dania_e16_s2192.pth   SoVITS_weights_v2ProPlus/dania_e16_s2192.pth
cp -f ../model/ref.wav               output/slicer_opt/
echo "  weights copied"

echo "== 3. python env (uv, py3.10) =="
export UV_PYTHON_INSTALL_MIRROR="https://registry.npmmirror.com/-/binary/python-build-standalone"
uv venv --python 3.10 .venv
uv pip install --python .venv torch==2.5.1 torchaudio==2.5.1 \
    --index-url https://download.pytorch.org/whl/cu124
echo "== 4. requirements =="
uv pip install --python .venv -r requirements.txt \
    --default-index https://mirrors.aliyun.com/pypi/simple
echo "DEPLOY-ENV-DONE"
