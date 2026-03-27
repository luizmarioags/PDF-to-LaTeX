# PDF2TEX_CODEX

Projeto para traduzir PDFs em lote para arquivos `.tex` em português do Brasil, usando a API da OpenAI e automação no VS Code.

## Estrutura
- `input/`: PDFs de entrada
- `output/`: arquivos `.tex` gerados
- `scripts/`: scripts Python
- `AGENTS.md`: regras do projeto para o Codex

## Execução
```bash
python scripts/batch_translate_pdfs.py input --output-dir output --recursive --overwrite
