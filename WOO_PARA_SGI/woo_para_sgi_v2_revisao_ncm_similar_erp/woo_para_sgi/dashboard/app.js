async function executar(){
  const limite = document.getElementById('limite').value || 20;
  const r = await fetch(`/executar?limite=${limite}`, {method:'POST'});
  const j = await r.json();
  alert(j.mensagem || 'Iniciado');
}

function setText(id, v){document.getElementById(id).textContent = v ?? 0}
function esc(v){return String(v ?? '').replace(/[&<>"]/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[s]))}

async function carregarStatus(){
  try{
    const r = await fetch('/status');
    const s = await r.json();
    setText('total', s.total || 0);
    setText('processados', s.processados || 0);
    setText('match_forte', s.match_forte || 0);
    setText('novos', s.novos || 0);
    setText('revisao', s.revisao || 0);
    setText('erros', s.erros || 0);
    document.getElementById('mensagem').textContent = s.mensagem || 'Aguardando...';
    document.getElementById('dry_run').textContent = s.dry_run === false ? 'MODO REAL' : 'DRY RUN SEGURO';
    const total = Number(s.total || 0), proc = Number(s.processados || 0);
    const perc = total ? Math.min(100, Math.round((proc/total)*100)) : 0;
    document.getElementById('progress').style.width = perc + '%';
  }catch(e){}
}

async function carregarLogs(){
  try{
    const r = await fetch('/logs');
    const j = await r.json();
    const el = document.getElementById('logs');
    el.textContent = (j.linhas || []).join('\n');
    el.scrollTop = el.scrollHeight;
  }catch(e){}
}

async function carregarRelatorios(){
  try{
    const r = await fetch('/relatorios');
    const j = await r.json();
    const box = document.getElementById('relatorios');
    box.innerHTML = '';
    (j.relatorios || []).forEach(rep => {
      const a = document.createElement('a');
      a.className = 'report-item';
      a.href = '/baixar/' + encodeURIComponent(rep.nome);
      a.textContent = rep.nome;
      box.appendChild(a);
    });
  }catch(e){}
}

function badgeStatus(status){
  const s = (status || '').toUpperCase();
  if(s === 'MATCH_FORTE') return '<span class="tag ok">MATCH FORTE</span>';
  if(s === 'MATCH_MEDIO') return '<span class="tag warn">MATCH MÉDIO</span>';
  if(s === 'NOVO') return '<span class="tag new">NOVO</span>';
  return `<span class="tag danger">${esc(s || 'REVISÃO')}</span>`;
}

async function decidir(item, acao){
  const observacao = prompt('Observação opcional:', '') || '';
  const payload = {
    ...item,
    acao,
    observacao,
    ncm_aprovado: item.ncm_sugerido || ''
  };
  const r = await fetch('/decidir', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(payload)
  });
  const j = await r.json();
  if(j.ok){
    alert('Decisão salva.');
    carregarRevisao();
  }else{
    alert('Não consegui salvar decisão.');
  }
}

function cardRevisao(item, idx){
  const ncm = item.ncm_sugerido || 'REVISAR';
  const fonte = item.ncm_fonte || '-';
  const erp = item.erp_codigo ? `${item.erp_codigo} • ${item.erp_descricao || ''}` : 'Sem ERP vinculado';
  return `
    <div class="review-card">
      <div class="review-top">
        <div>${badgeStatus(item.status)} <span class="score">Score ${Number(item.score || 0).toFixed(2)}</span></div>
        <small>SKU: ${esc(item.sku || '-')}</small>
      </div>
      <h3>${esc(item.nome || '')}</h3>
      <div class="compare">
        <div><b>Woo</b><p>${esc(item.nome_original_woo || item.nome || '')}</p></div>
        <div><b>ERP melhor similar</b><p>${esc(erp)}</p><small>Ref: ${esc(item.erp_referencia || '-')} | Marca: ${esc(item.erp_marca || '-')}</small></div>
        <div><b>NCM V2</b><p>${esc(ncm)} <span class="mini">${esc(item.ncm_confianca || '')}</span></p><small>Fonte: ${esc(fonte)}<br>${esc(item.ncm_motivo || '')}</small></div>
      </div>
      <div class="btn-row">
        <button onclick='decidir(window.__revisao[${idx}], "APROVAR_ATUALIZACAO")'>Aprovar atualização</button>
        <button onclick='decidir(window.__revisao[${idx}], "CADASTRAR_NOVO")' class="secondary">Cadastrar novo</button>
        <button onclick='decidir(window.__revisao[${idx}], "REVISAR_NCM")' class="secondary">Revisar NCM</button>
        <button onclick='decidir(window.__revisao[${idx}], "IGNORAR")' class="dangerBtn">Ignorar</button>
      </div>
    </div>
  `;
}

async function carregarRevisao(){
  try{
    const r = await fetch('/revisao');
    const j = await r.json();
    window.__revisao = j.itens || [];
    document.getElementById('revisaoResumo').textContent = `Relatório: ${j.arquivo || 'nenhum'} • Itens para revisão: ${window.__revisao.length} • Vínculos salvos: ${Object.keys(j.vinculos || {}).length}`;
    document.getElementById('listaRevisao').innerHTML = window.__revisao.map(cardRevisao).join('') || '<div class="empty">Nenhum item pendente no último relatório.</div>';
  }catch(e){
    document.getElementById('revisaoResumo').textContent = 'Erro ao carregar revisão.';
  }
}

setInterval(()=>{carregarStatus();carregarLogs();carregarRelatorios()}, 2500);
setInterval(carregarRevisao, 8000);
carregarStatus();carregarLogs();carregarRelatorios();carregarRevisao();
