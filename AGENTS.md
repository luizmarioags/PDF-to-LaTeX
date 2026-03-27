# Regras do projeto PDF -> TEX

## Objetivo
Converter PDFs em arquivos .tex traduzidos para português do Brasil.

## Regras obrigatórias
- Nunca compilar os arquivos .tex.
- Gerar sempre um .tex com o mesmo nome-base do PDF.
- Usar exatamente o preâmbulo definido pelo usuário.
- Preencher título, autor e data a partir do PDF quando possível.
- Se esses dados não estiverem claros, usar:
  - Titulo do Texto que foi Traduzido
  - Autor do Texto
  - Data de Publicação
- Preservar fórmulas, seções, listas, notas e tabelas.
- Não usar markdown na saída final do LaTeX.
- Fazer mudanças mínimas e previsíveis nos scripts.