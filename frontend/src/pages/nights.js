import { api } from '../api/workspace.js';
import { table } from '../components/common/table.js';
import { empty, exportButton, heading } from '../components/common/heading.js';
import { auditActions } from '../constants/enums.js';
import { bindForm, notice } from '../hooks/forms.js';
import { navigate } from '../router/routes.js';
import { escapeHtml as e, timeText } from '../utils/format.js';

const activeState = { active: 'succeeded', superseded: 'hold' };

function quotaBar(night) {
  const share = night.capacity ? Math.min(100, 100 * night.dispatched / night.capacity) : 0;
  return `<div class="quota" role="img" aria-label="已签 ${night.dispatched} 张，共 ${night.capacity} 个名额">
    <div class="quota-head"><strong>${night.dispatched} / ${night.capacity}</strong>
    <span class="muted">本晚已签发 ${night.dispatched} 张，还剩 ${night.remaining} 张</span></div>
    <span class="track"><i style="--amount:${share}%"></i></span></div>`;
}

function policyTable(quota) {
  return `<div class="table-scroll" tabindex="0"><table><caption class="muted">
    定剪枝历史上各派法在 ${quota.tune_quota} 张限额下的总误派代价</caption>
    <thead><tr><th scope="col">派法</th><th scope="col">派出</th><th scope="col">漏派</th><th scope="col">白跑</th><th scope="col">总代价</th></tr></thead>
    <tbody>${quota.policies.map(row => `<tr ${row.key === quota.policy ? 'class="chosen"' : ''}>
      <td>${e(row.label)}${row.key === quota.policy ? ' · 选用' : ''}</td>
      <td>${row.dispatched}</td><td>${row.missed}</td><td>${row.unnecessary}</td><td>${row.cost}</td></tr>`).join('')}</tbody>
    </table></div>`;
}

function listTimeline(lists) {
  if (!lists?.length) return '<p class="muted">本晚还没有启用的补拍清单。</p>';
  return `<ol class="timeline">${lists.map(item => `<li>
    <span class="status s-${activeState[item.state] ?? 'hold'}">${item.state === 'active' ? '启用中' : '已替代'}</span>
    <strong>v${item.version}</strong><span class="muted">${item.count} 张入列 · ${item.trimmed_count} 张名额外 · ${e(timeText(item.created_at))}</span>
    <a href="#results/${item.run_id}">来源计算单</a></li>`).join('')}</ol>`;
}

export async function nightsPage(profile, account, id) {
  const [nights, runs, audit] = await Promise.all([api.nights(), api.runs(), api.audit()]);
  const current = nights.find(item => item.id === id) || nights[0];
  const detail = current && await api.night(current.id);
  const active = detail?.active;
  const succeeded = runs.filter(run => run.status === 'succeeded' && run.night_id === current?.id);
  const versions = detail?.lists || [];
  const existingIds = new Set(versions.map(item => item.run_id));

  const createForm = account.role === 'analyst' ? `<details class="intake" ${nights.length ? '' : 'open'}>
    <summary>新建晚场</summary><form id="night-form">
      <label>晚场编号<input name="key" maxlength="40" placeholder="huai-night-20261126" required></label>
      <label>晚场名称<input name="name" maxlength="100" required></label>
      <label>本晚补拍名额<input type="number" name="capacity" min="0" max="500" step="1" value="6" required></label>
      <div class="form-error" data-error role="alert"></div><button type="submit">保存晚场</button></form></details>` : '';

  const activateForm = account.role === 'reviewer' && current ? `<form id="activate-form">
    <label>选择要启用的计算单<select name="run_id">${succeeded.map(run =>
      `<option value="${run.id}" ${existingIds.has(run.id) ? 'disabled' : ''}>${e(run.label)} · ${e(run.status)}${existingIds.has(run.id) ? ' · 已启用' : ''}</option>`).join('')}</select></label>
    <p class="muted">启用后旧版清单自动替代。若重算失败，领班继续用原清单；签发已占用的名额会从新版中扣除。</p>
    <div class="form-error" data-error role="alert"></div>
    <button type="submit" ${succeeded.some(run => !existingIds.has(run.id)) ? '' : 'disabled'}>启用为新版</button></form>` : '';

  let rows = [];
  let plan = null;
  if (active) {
    const source = await api.run(active.run_id);
    const byId = new Map((source.result?.rows || []).map(row => [row.sample_id, row]));
    rows = (active.samples || []).map(sample => byId.get(sample)).filter(Boolean);
    plan = source.result?.quota || null;
  }

  const body = current ? `<div class="board"><aside class="side">
      <h2>晚场</h2>${nights.map(item => `<a class="version ${item.id === current.id ? 'current' : ''}" href="#nights/${item.id}">
        <strong>${e(item.name)}</strong><span>${item.dispatched}/${item.capacity} · ${e(item.key)}</span></a>`).join('')}
      ${createForm}
      ${activateForm ? `<h3>启用新版</h3>${activateForm}` : ''}
    </aside><section class="work">
      <h2>${e(detail.name)}</h2>
      ${quotaBar(detail)}
      ${active ? `<div class="work-head"><h2>当前清单 v${active.version}</h2>
        ${exportButton('/nights/' + current.id + '/dispatch.csv', 'dispatch.csv', '导出补拍清单')}</div>
        ${rows.length ? table([
          {key:'sample_id',label:'照片号'}, {key:'station',label:'布点'}, {key:'decision',label:'派发决定'},
          {key:'risk',label:'同叶历史补拍（%）'}, {key:'action',label:'现场处理'},
        ], rows) : '<p class="muted">当前清单没有可派出的照片。</p>'}
        ${active.trimmed_count ? `<p class="muted">因名额或已签发，${active.trimmed_count} 张被列入名额外。</p>` : ''}` :
        empty('本晚还没有补拍清单', '先在分流试算中完成计算，再由复核员启用为新版清单。')}
      ${plan ? `<h3>限额下的派法比较</h3>${policyTable(plan)}
        <dl class="metrics">
          <div><dt>独立复盘漏派</dt><dd>${plan.audit.missed}</dd></div>
          <div><dt>独立复盘白跑</dt><dd>${plan.audit.unnecessary}</dd></div>
          <div><dt>复盘总误派代价</dt><dd>${plan.audit.cost}</dd></div>
          <div><dt>全部留用代价</dt><dd>${plan.baselines.none.cost}</dd></div>
          <div><dt>全部补拍代价</dt><dd>${plan.baselines.all.cost}</dd></div>
        </dl>` : ''}
      <h3>已签发照片</h3>
      ${detail.dispatches.length ? table([
        {key:'sample_id',label:'照片号'}, {key:'reviewer',label:'签发人'}, {key:'created_at',label:'时间'},
      ], detail.dispatches, (row, column, value) => column.key === 'created_at' ? e(timeText(value)) : e(value)) :
        '<p class="muted">还没有签发任何照片。</p>'}
      <h3>清单版本</h3>${listTimeline(detail.lists)}
      <h3>审计流水</h3>
      ${audit.length ? table([
        {key:'action',label:'动作'}, {key:'actor',label:'操作者'}, {key:'subject',label:'对象'}, {key:'created_at',label:'时间'},
      ], audit.slice(0, 30), (row, column, value) => {
        if (column.key === 'action') return e(auditActions[value] || value);
        if (column.key === 'subject') return e(value.slice(0, 8));
        if (column.key === 'created_at') return e(timeText(value));
        return e(value);
      }) : '<p class="muted">暂无审计事件。</p>'}
    </section></div>` :
    empty('还没有晚场', '分析员可先创建一个晚场，再为它提交分流试算。');

  return {
    html: heading(profile.labels.nights, '按漏派和白跑的代价挑选照片，在开场前把限额内的补拍清单派给巡拍班。') + body,
    mount(root, refresh) {
      bindForm(root, 'night-form', async data => {
        const saved = await api.createNight({
          key: data.get('key'), name: data.get('name'), capacity: Number(data.get('capacity')),
        });
        notice('晚场已创建。');
        navigate('nights', saved.id);
      });
      bindForm(root, 'activate-form', async data => {
        const runId = data.get('run_id');
        if (!runId) throw new Error('请选择一张计算成功的计算单。');
        const listing = await api.activate(current.id, runId);
        notice(`已启用 v${listing.version}，共 ${listing.count} 张补拍。`);
        refresh();
      });
    },
  };
}
