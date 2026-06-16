# WooCommerce → SGI/Sólidus Smart — V2 Revisão + NCM por similar do ERP

Esta versão continua segura (`DRY_RUN=true`) e não salva/cadastra nada no ERP automaticamente.

## O que mudou na V2

- O robô continua lendo produtos do WooCommerce e pesquisando no SGI via Selenium.
- Mantém somente 2 buscas no SGI:
  1. `buscar_por_referencia_isolada()` com `%` na frente.
  2. `buscar_por_marca_modelo()` com `%` na frente.
- Após login, trata a tela `/login/informa_local_de_trabalho` e clica em `PROSSEGUIR`.
- O limite padrão está em 20 produtos.
- O NCM final agora segue esta prioridade:
  1. Se for `MATCH_FORTE`, usa o NCM do produto ERP correspondente.
  2. Se for `MATCH_MEDIO` ou `REVISAO` e houver produto similar com NCM, sugere o NCM do similar, mas exige revisão.
  3. Se não houver similar útil, aplica regras internas conservadoras.
  4. Se houver dúvida, mantém `REVISAR`.
- O dashboard ganhou **Painel de revisão** com botões:
  - Aprovar atualização
  - Cadastrar novo
  - Revisar NCM
  - Ignorar

As decisões ficam salvas em:

```text
storage/revisoes/decisoes_revisao.json
storage/revisoes/vinculos_woo_sgi.json
```

## Como rodar

```bat
rodar_dashboard.bat
```

Depois abra o dashboard e clique em **Executar simulação**.

## Importante sobre NCM

NCM é informação fiscal. Esta V2 sugere NCM por histórico do próprio ERP e por regras internas, mas mantém revisão quando a confiança não é alta. Não libere gravação real de NCM sem validação fiscal.
