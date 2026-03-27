#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

from google import genai


DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")


def strip_code_fences(text: str) -> str:
    text = text.strip()
    match = re.match(
        r"^```(?:latex|tex)?\s*(.*?)\s*```$",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return text


def list_pdf_files(input_dir: Path, recursive: bool = False) -> List[Path]:
    if not input_dir.exists():
        raise FileNotFoundError(f"Diretório não encontrado: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"O caminho não é um diretório: {input_dir}")

    pattern = "**/*.pdf" if recursive else "*.pdf"
    pdfs = sorted(input_dir.glob(pattern))

    if not pdfs:
        raise FileNotFoundError(f"Nenhum PDF encontrado em: {input_dir}")

    return pdfs


def make_output_path(pdf_path: Path, input_dir: Path, output_dir: Optional[Path]) -> Path:
    """
    Gera sempre o .tex com o mesmo nome-base do PDF.

    Se output_dir for informado:
      input/sub/doc.pdf -> output_dir/sub/doc.tex

    Se output_dir for omitido:
      input/sub/doc.pdf -> input/sub/doc.tex
    """
    tex_name = f"{pdf_path.stem}.tex"

    if output_dir is None:
        return pdf_path.with_name(tex_name)

    relative_parent = pdf_path.parent.relative_to(input_dir)
    final_dir = output_dir / relative_parent
    final_dir.mkdir(parents=True, exist_ok=True)
    return final_dir / tex_name


def build_prompt(pdf_name: str, tex_name: str, extra_instructions: str) -> str:
    return rf"""
Traduza integralmente o PDF anexado para português do Brasil e gere um arquivo LaTeX completo.

Requisitos específicos:
- Nome do PDF de origem: {pdf_name}
- Nome esperado do arquivo .tex: {tex_name}
- O arquivo .tex deve ter exatamente o mesmo nome-base do PDF.
- Gere um documento completo, começando com \documentclass e terminando com \end{{document}}.
- Use exatamente este preâmbulo estrutural:

\documentclass[12pt]{{article}}

\usepackage[T1]{{fontenc}}
\usepackage[utf8]{{inputenc}}
\usepackage[brazil]{{babel}}
\usepackage{{lmodern}}
\usepackage{{microtype}}
\usepackage[a4paper,margin=2.5cm]{{geometry}}
\usepackage{{setspace}}
\usepackage{{indentfirst}}

\setstretch{{1.15}}

\title{{TITULO_AQUI \thanks{{Texto Traduzido livremente por Luiz Mario Andrade com o auxílio da ferramenta Chat GPT 5.4}}}}
\author{{AUTOR_AQUI}}
\date{{DATA_AQUI}}

\begin{{document}}

\maketitle

- Substitua TITULO_AQUI pelo título do texto traduzido.
- Substitua AUTOR_AQUI pelo autor do texto.
- Substitua DATA_AQUI pela data de publicação.
- Se alguma dessas três informações não estiver clara no PDF, use respectivamente:
  - Titulo do Texto que foi Traduzido
  - Autor do Texto
  - Data de Publicação
- Preserve equações, seções, subseções, listas, notas e tabelas.
- Preserve a estrutura do documento original.
- Não use markdown.
- Não use cercas de código.
- Entregue apenas o conteúdo do .tex.
- Feche corretamente o documento com \end{{document}}.

Instruções adicionais:
- Preserve termos técnicos com máxima fidelidade.
- Não resuma.
- Não omita conteúdo relevante.
- Se houver ambiguidades no PDF, reconstrua da forma mais fiel possível sem inventar conteúdo.
- Preserve referências bibliográficas, notas e citações.
- Escape corretamente caracteres especiais do LaTeX quando necessário.

Instruções extras:
{extra_instructions}
""".strip()


def is_retryable_error(error_message: str) -> bool:
    msg = error_message.lower()

    retry_markers = [
        "503",
        "unavailable",
        "server disconnected without sending a response",
        "timeout",
        "timed out",
        "deadline exceeded",
        "connection reset",
        "connection aborted",
        "temporarily unavailable",
        "internal error",
        "500",
        "502",
        "504",
        "resource exhausted",
        "429",
        "rate limit",
        "too many requests",
    ]

    return any(marker in msg for marker in retry_markers)


def write_status_log(log_path: Path, rows: List[List[str]]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as f:
        f.write("arquivo_pdf\tarquivo_tex\tstatus\tmensagem\n")
        for row in rows:
            safe_row = [str(col).replace("\t", " ").replace("\n", " ") for col in row]
            f.write("\t".join(safe_row) + "\n")


def translate_pdf_to_tex(
    client: genai.Client,
    pdf_path: Path,
    tex_path: Path,
    model: str,
    extra_instructions: str,
    max_retries: int = 6,
    base_sleep: float = 3.0,
) -> None:
    """
    Faz upload do PDF para o Gemini, solicita a tradução para LaTeX
    e salva o .tex. Inclui retry com exponential backoff para falhas transitórias.
    """
    tex_path.parent.mkdir(parents=True, exist_ok=True)

    prompt = build_prompt(
        pdf_name=pdf_path.name,
        tex_name=tex_path.name,
        extra_instructions=extra_instructions,
    )

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            uploaded = client.files.upload(
                file=str(pdf_path),
                config={"mime_type": "application/pdf"},
            )

            response = client.models.generate_content(
                model=model,
                contents=[uploaded, prompt],
            )

            output_text = strip_code_fences(getattr(response, "text", "") or "")

            if not output_text.strip():
                raise RuntimeError("O modelo retornou saída vazia.")

            tex_path.write_text(output_text, encoding="utf-8")
            return

        except Exception as e:
            last_error = e
            err_msg = str(e)

            if not is_retryable_error(err_msg):
                raise

            if attempt == max_retries:
                break

            sleep_time = min(base_sleep * (2 ** (attempt - 1)), 90.0)
            sleep_time += random.uniform(0, 2)

            print(
                f"  Tentativa {attempt}/{max_retries} falhou para {pdf_path.name}: {e}\n"
                f"  Aguardando {sleep_time:.1f}s antes de tentar novamente..."
            )
            time.sleep(sleep_time)

    raise RuntimeError(f"Falha após {max_retries} tentativas: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Traduz PDFs em lote com Gemini e gera .tex com o mesmo nome-base."
    )

    parser.add_argument(
        "input_dir",
        help="Diretório com os PDFs."
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Diretório de saída. Se omitido, salva o .tex ao lado de cada PDF."
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Busca PDFs também em subpastas."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Modelo Gemini. Padrão: {DEFAULT_MODEL}"
    )
    parser.add_argument(
        "--extra-instructions",
        default="Preserve integralmente a estrutura do original e mantenha terminologia técnica consistente.",
        help="Instruções extras."
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Sobrescreve arquivos .tex existentes."
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=3.0,
        help="Pausa entre arquivos, em segundos. Padrão: 3."
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=6,
        help="Número máximo de tentativas por arquivo em caso de erro transitório. Padrão: 6."
    )
    parser.add_argument(
        "--base-retry-sleep",
        type=float,
        default=3.0,
        help="Tempo base do backoff exponencial. Padrão: 3."
    )

    args = parser.parse_args()

    if not os.getenv("GEMINI_API_KEY"):
        print("ERRO: defina GEMINI_API_KEY no ambiente.", file=sys.stderr)
        return 1

    input_dir = Path(args.input_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None

    try:
        pdfs = list_pdf_files(input_dir, recursive=args.recursive)
    except Exception as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    total = len(pdfs)
    ok = 0
    failed = 0
    skipped = 0
    status_rows: List[List[str]] = []

    status_log_path = (output_dir if output_dir else input_dir) / "translation_status.tsv"
    failed_log_path = (output_dir if output_dir else input_dir) / "failed_translations.log"

    print(f"Encontrados {total} PDF(s).")
    print("-" * 60)

    failed_entries: List[str] = []

    for idx, pdf_path in enumerate(pdfs, start=1):
        tex_path = make_output_path(pdf_path, input_dir, output_dir)

        if tex_path.exists() and not args.overwrite:
            skipped += 1
            print(f"[{idx}/{total}] SKIP  {pdf_path.name} -> {tex_path.name} (já existe)")
            status_rows.append([pdf_path.name, tex_path.name, "SKIP", "arquivo .tex já existe"])
            write_status_log(status_log_path, status_rows)
            continue

        print(f"[{idx}/{total}] INÍCIO {pdf_path.name}")

        try:
            translate_pdf_to_tex(
                client=client,
                pdf_path=pdf_path,
                tex_path=tex_path,
                model=args.model,
                extra_instructions=args.extra_instructions,
                max_retries=args.max_retries,
                base_sleep=args.base_retry_sleep,
            )
            ok += 1
            print(f"[{idx}/{total}] OK     {pdf_path.name} -> {tex_path.name}")
            status_rows.append([pdf_path.name, tex_path.name, "OK", "traduzido com sucesso"])

        except Exception as e:
            failed += 1
            err_msg = str(e)
            print(f"[{idx}/{total}] FAIL   {pdf_path.name} -> {err_msg}", file=sys.stderr)
            status_rows.append([pdf_path.name, tex_path.name, "FAIL", err_msg])
            failed_entries.append(f"{pdf_path.name}\t{err_msg}")

        write_status_log(status_log_path, status_rows)

        if args.sleep_seconds > 0 and idx < total:
            time.sleep(args.sleep_seconds)

    if failed_entries:
        with failed_log_path.open("w", encoding="utf-8") as f:
            for line in failed_entries:
                f.write(line + "\n")

    print("-" * 60)
    print(
        f"Concluído. Sucessos: {ok} | Falhas: {failed} | Pulados: {skipped} | Total: {total}"
    )

    print(f"Status detalhado salvo em: {status_log_path}")
    if failed_entries:
        print(f"Log de falhas salvo em: {failed_log_path}")

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())