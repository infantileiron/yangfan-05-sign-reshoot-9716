import { request } from './client.js';

export const api = {
  signIn: data => request('/auth/login', { method: 'POST', body: data }),
  profile: () => request('/profile'),
  datasets: () => request('/datasets'),
  dataset: id => request('/datasets/' + id),
  upload: data => request('/datasets', { method: 'POST', body: data }),
  runs: () => request('/runs'),
  run: id => request('/runs/' + id),
  submit: data => request('/runs', { method: 'POST', body: data }),
  recompute: (id, data = {}) => request('/runs/' + id + '/recompute', { method: 'POST', body: data }),
  nights: () => request('/nights'),
  night: id => request('/nights/' + id),
  createNight: data => request('/nights', { method: 'POST', body: data }),
  dispatchList: id => request('/nights/' + id + '/dispatch-list'),
  activate: (id, runId) => request('/nights/' + id + '/dispatch-list', { method: 'POST', body: { run_id: runId } }),
  review: (id, data) => request('/runs/' + id + '/review', { method: 'POST', body: data }),
  reviews: () => request('/reviews'),
  audit: () => request('/audit'),
  download: path => request(path, { download: true }),
};
