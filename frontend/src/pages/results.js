import { api } from '../api/workspace.js';
import { resultChart } from '../components/chart.js';
import { empty, exportButton, heading } from '../components/common/heading.js';
import { status } from '../components/common/status.js';
import { table } from '../components/common/table.js';
import { bindForm, notice } from '../hooks/forms.js';
import { navigate } from '../router/routes.js';
import { escapeHtml as e, shortId, timeText } from '../utils/format.js';

export async function resultsPage(profile, account, id) {
  const runs = await api.runs();
  const chosen = id || runs[0]?.id;
  if (!chosen) return { html: heading(profile.labels.results, profile.algorithm) +
    empty('还没有计算结果', '创建计算单，等待后台完成计算。', '<a href="#runs">回计算页面</a>') };
  const [run, datasets] = await Promise.all([api.run(chosen), api.datasets()]);
  const selector = runs.map(item => `<option value="${item.id}" ${item.id === run.id ? 'selected' : ''}>
      ${e(item.label)} · ${e(shortId(item.id))}</option>`).join('');
  const actions = run.result ? exportButton('/runs/' + run.id + '/csv', 'analysis.csv', '导出计算结果') : '';
  const intro = heading(profile.labels.results, profile.labels.action, actions) +
    `<div class="result-pick"><label>计算单<select id="choose-result">${selector}</select></label>
    ${status(run.status)}<span class="muted">${e(timeText(run.created_at))}</span></div>`;
  const mount = root => {
    root.querySelector('#choose-result').onchange = event => { location.hash = '#results/' + event.target.value; };
  };
  if (!run.result) {
    const retry = account.role === 'analyst' && run.night_id && run.status === 'failed' ?
      `<form id="recompute-form"><button type="submit">按原输入重试计算</button>
       <p class="muted">重算未成功前，领班继续使用原补拍清单，已签发照片仍占本晚名额。</p></form>` : '';
    return {
      html: intro + (run.status === 'failed' ?
        empty('计算失败', run.error, retry) :
        `<div class="empty"><h2>等待后台计算</h2><p>页面会自动更新当前计算状态。</p></div>`),
      mount(root, refresh) {
        mount(root);
        bindForm(root, 'recompute-form', async () => {
          const clone = await api.recompute(run.id);
          notice('已重新提交计算。');
          navigate('results', clone.id);
        });
      },
      poll: ['queued', 'running'].includes(run.status),
    };
  }
  const result = run.result;
  const quota = result.quota;
  const nightLine = run.night_id ? `<dt>晚场</dt><dd><a href="#nights/${run.night_id}">剩余名额 ${quota?.remaining ?? '—'}</a></dd>` : '';
  const recompute = account.role === 'analyst' && run.night_id ? `<details class="intake"><summary>补录后重算</summary>
    <form id="recompute-form" class="inline-form">
      <label>数据版本<select name="dataset_id">${datasets.map(item =>
        `<option value="${item.id}" ${item.id === run.dataset_id ? 'selected' : ''}>${e(item.name)} · ${item.count} 行</option>`).join('')}</select></label>
      <p class="muted">晚到的测量数据导入为新版本后，可在这里选它重算。重算成功再启用新版清单；失败可重试，领班继续用原清单。</p>
      <div class="form-error" data-error role="alert"></div>
      <button class="quiet" type="submit">按所选数据重算</button></form></details>` : '';
  return {
    html: intro + `<div class="board results-board"><aside class="side">
      <h2>本次口径</h2><dl class="meta"><dt>${e(profile.parameter.label)}</dt><dd>${e(run.parameter)}</dd>
      <dt>数据版本</dt><dd><a href="#datasets/${run.dataset_id}">${shortId(run.dataset_id)}</a></dd>
      ${nightLine}
      </dl><p class="muted">${e(profile.downstream)}</p>
      <a class="button" href="#handoff/${run.id}">查看签审</a>${recompute}
      </aside><section class="work">
      <h2>${e(result.summary)}</h2>
      ${quota ? `<p class="muted">本晚限额 ${quota.capacity} 张，已签发 ${quota.dispatched} 张，本次按「${e(quota.policy_label)}」派 ${quota.selected.length} 张。
        在定剪枝历史折算的 ${quota.tune_quota} 张限额上比较后选定此派法，独立复盘按 ${quota.audit.quota} 张验收。</p>` : ''}
      <dl class="metrics">${result.metrics.map(metric => `<div><dt>${e(metric.label)}</dt><dd>${e(metric.value)}</dd></div>`).join('')}</dl>
      ${resultChart(result.rows, profile.chart)}
      <h3>${e(profile.labels.action)}</h3>
      ${table(profile.result_columns, result.rows, (row, column, value) =>
        column.key === 'decision' ? `<span class="status s-${value === '补拍' ? 'approve' : value === '候补' ? 'hold' : 'succeeded'}">${e(value)}</span>` : e(value))}
      ${quota ? `<details class="details"><summary>限额下的派法比较</summary>
        ${table([{key:'label',label:'派法'},{key:'dispatched',label:'派出'},{key:'missed',label:'漏派'},
          {key:'unnecessary',label:'白跑'},{key:'cost',label:'总代价'}], quota.policies, (row, column, value) =>
          column.key === 'label' ? e(value) + (row.key === quota.policy ? ' · 选用' : '') : e(value))}
        <p class="muted">在定剪枝历史折算的 ${quota.tune_quota} 张限额上比较，再用独立复盘 ${quota.audit.quota} 张验收。</p></details>` : ''}
      <details class="details"><summary>计算说明</summary><ul>${result.notes.map(note => '<li>' + e(note) + '</li>').join('')}</ul></details>
      </section></div>`,
    mount(root, refresh) {
      mount(root);
      bindForm(root, 'recompute-form', async data => {
        const clone = await api.recompute(run.id, { dataset_id: data.get('dataset_id') || null });
        notice('已按所选数据重新提交计算。');
        navigate('results', clone.id);
      });
    },
  };
}
