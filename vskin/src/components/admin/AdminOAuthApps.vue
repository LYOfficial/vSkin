<template>
  <div class="oauth-admin-section animate-fade-in">
    <div class="page-header">
      <div class="page-header-content">
        <div class="page-header-icon"><Link /></div>
        <div class="page-header-text">
          <h2>OAuth 2 应用管理</h2>
          <p class="subtitle">为外部平台创建应用，并在这里直接完成设备授权流配置</p>
        </div>
      </div>
      <div class="page-header-actions">
        <el-button @click="openCreateDeviceDialog">新增授权设备应用</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreateDialog">新增应用</el-button>
      </div>
    </div>

    <el-card class="surface-card mb-6" shadow="never">
      <template #header>
        <div class="card-header-flex">
          <span>接口地址与样例</span>
          <el-button text :icon="Refresh" @click="loadData">刷新</el-button>
        </div>
      </template>
      <div class="meta-grid">
        <div class="meta-item">
          <div class="meta-label">授权地址</div>
          <el-input readonly :model-value="meta.authorize_endpoint" />
        </div>
        <div class="meta-item">
          <div class="meta-label">令牌地址</div>
          <el-input readonly :model-value="meta.token_endpoint" />
        </div>
        <div class="meta-item">
          <div class="meta-label">用户信息地址</div>
          <el-input readonly :model-value="meta.userinfo_endpoint" />
        </div>
        <div class="meta-item">
          <div class="meta-label">回调地址样例</div>
          <el-input readonly :model-value="meta.sample_redirect_uri" />
        </div>
        <div class="meta-item">
          <div class="meta-label">设备授权地址</div>
          <el-input readonly :model-value="meta.device_authorization_endpoint" />
        </div>
        <div class="meta-item">
          <div class="meta-label">OpenID 配置地址</div>
          <el-input readonly :model-value="meta.openid_configuration_url" />
        </div>
        <div class="meta-item">
          <div class="meta-label">JWKS 地址</div>
          <el-input readonly :model-value="meta.jwks_uri" />
        </div>
        <div class="meta-item">
          <div class="meta-label">浏览器授权页</div>
          <el-input readonly :model-value="meta.verification_uri" />
        </div>
      </div>
    </el-card>

    <el-card class="surface-card mb-6" shadow="never">
      <template #header>
        <div class="card-header-flex">
          <span>设备授权流设置</span>
          <el-button text :icon="Refresh" @click="loadData">刷新</el-button>
        </div>
      </template>
      <el-form label-position="top" :model="deviceSettings">
        <div class="meta-grid">
          <div class="meta-item">
            <div class="meta-label">授权设备共享客户端</div>
            <el-select v-model="deviceSettings.shared_client_ids" multiple clearable collapse-tags collapse-tags-tooltip placeholder="选择可用于设备授权流的 OAuth 应用">
              <el-option v-for="app in apps" :key="app.app_id" :label="`${app.app_id} - ${app.client_name || '未命名应用'}`" :value="app.app_id" />
            </el-select>
            <p class="hint-text">这里允许选择多个客户端。OpenID 配置会保留兼容字段 shared_client_id，同时新增 shared_client_ids。</p>
          </div>
          <div class="meta-item">
            <div class="meta-label">设备码有效期（秒）</div>
            <el-input-number v-model="deviceSettings.expires_in" :min="300" :step="60" />
          </div>
          <div class="meta-item">
            <div class="meta-label">轮询间隔（秒）</div>
            <el-input-number v-model="deviceSettings.interval" :min="5" :step="1" />
          </div>
          <div class="meta-item">
            <div class="meta-label">设备流默认回调 URL</div>
            <el-input v-model="deviceSettings.default_redirect_uri" placeholder="https://oauth.ustb.world/" />
            <p class="hint-text">设备授权流不会使用这个地址回调浏览器，它只需要是一个合法的 http(s) 地址。默认可直接填写 https://oauth.ustb.world/。这个地址不需要可访问，也不需要由你控制。</p>
          </div>
        </div>
      </el-form>
      <div class="device-settings-actions">
        <el-button type="primary" :loading="savingDeviceSettings" @click="saveDeviceSettings">保存设备授权设置</el-button>
      </div>
    </el-card>

    <el-card class="surface-card" shadow="never">
      <template #header>
        <div class="card-header-flex">
          <span>已创建应用</span>
          <el-tag type="info" effect="plain">共 {{ apps.length }} 个</el-tag>
        </div>
      </template>

      <el-table :data="apps" style="width: 100%" empty-text="暂无 OAuth 应用">
        <el-table-column prop="app_id" label="AppID" width="100" />
        <el-table-column prop="client_name" label="应用名称" min-width="180">
          <template #default="{ row }">
            <div class="app-name-cell">
              <span>{{ row.client_name || '未命名应用' }}</span>
              <el-tag v-if="row.is_device_shared_client" size="small" type="success">授权设备共享客户端</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="redirect_uri" label="回调 URL" min-width="280" />
        <el-table-column label="操作" width="360" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="success" plain @click="toggleSharedClient(row)">{{ row.is_device_shared_client ? '移出设备授权' : '加入设备授权' }}</el-button>
            <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button size="small" type="warning" @click="resetSecret(row)">重置 Secret</el-button>
            <el-button size="small" type="danger" @click="removeApp(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEditing ? '编辑 OAuth 应用' : '新增 OAuth 应用'" width="560px" append-to-body align-center>
      <el-form label-position="top" :model="form">
        <el-form-item label="应用名称">
          <el-input v-model="form.client_name" placeholder="例如：论坛登录" />
        </el-form-item>
        <el-form-item label="回调 URL">
          <el-input v-model="form.redirect_uri" placeholder="https://your-app.example.com/oauth/callback" />
          <p class="hint-text">授权码模式必须填写真实回调地址。设备授权流不会用到回调，可直接填写 https://oauth.ustb.world/。</p>
        </el-form-item>
        <el-form-item>
          <el-switch v-model="form.set_as_device_shared_client" />
          <span class="form-inline-label">设为授权设备共享客户端</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="secretDialogVisible" title="请保存新的 Client Secret" width="560px" append-to-body align-center>
      <p class="secret-tip">安全提示：该 secret 仅会在当前窗口完整展示一次。</p>
      <el-input readonly :model-value="newSecret" />
      <template #footer>
        <el-button @click="copySecret">复制 Secret</el-button>
        <el-button type="primary" @click="secretDialogVisible = false">我已保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Link, Plus, Refresh } from '@element-plus/icons-vue'

const apps = ref([])
const meta = reactive({
  authorize_endpoint: '',
  token_endpoint: '',
  device_authorization_endpoint: '',
  openid_configuration_url: '',
  jwks_uri: '',
  verification_uri: '',
  userinfo_endpoint: '',
  sample_redirect_uri: 'https://your-app.example.com/oauth/callback',
})

const deviceSettings = reactive({
  shared_client_ids: [],
  shared_client_id: null,
  expires_in: 900,
  interval: 5,
  default_redirect_uri: 'https://oauth.ustb.world/',
})

const dialogVisible = ref(false)
const secretDialogVisible = ref(false)
const isEditing = ref(false)
const saving = ref(false)
const savingDeviceSettings = ref(false)
const currentAppId = ref(null)
const newSecret = ref('')

const form = reactive({
  client_name: '',
  redirect_uri: '',
  set_as_device_shared_client: false,
})

const authHeaders = () => ({ Authorization: 'Bearer ' + localStorage.getItem('jwt') })

function normalizeDeviceSettings(payload) {
  const sharedIds = Array.isArray(payload?.shared_client_ids)
    ? payload.shared_client_ids.map(item => Number(item)).filter(item => Number.isInteger(item) && item > 0)
    : payload?.shared_client_id
      ? [Number(payload.shared_client_id)].filter(item => Number.isInteger(item) && item > 0)
      : []

  return {
    shared_client_ids: [...new Set(sharedIds)],
    shared_client_id: sharedIds[0] ?? null,
    expires_in: Number(payload?.expires_in) || 900,
    interval: Number(payload?.interval) || 5,
    default_redirect_uri: payload?.default_redirect_uri || 'https://oauth.ustb.world/',
  }
}

function isDeviceSharedClient(appId) {
  return deviceSettings.shared_client_ids.includes(Number(appId))
}

async function loadData() {
  try {
    const [metaRes, appsRes, deviceSettingsRes] = await Promise.all([
      axios.get('/admin/oauth/meta', { headers: authHeaders() }),
      axios.get('/admin/oauth/apps', { headers: authHeaders() }),
      axios.get('/admin/oauth/device-settings', { headers: authHeaders() }),
    ])
    Object.assign(meta, metaRes.data || {})
    apps.value = (appsRes.data || []).sort((a, b) => Number(a.app_id) - Number(b.app_id))
    Object.assign(deviceSettings, normalizeDeviceSettings(deviceSettingsRes.data || {}))
  } catch (e) {
    ElMessage.error('加载 OAuth 应用失败')
  }
}

function openCreateDialog() {
  isEditing.value = false
  currentAppId.value = null
  form.client_name = ''
  form.redirect_uri = meta.sample_redirect_uri || 'https://your-app.example.com/oauth/callback'
  form.set_as_device_shared_client = false
  dialogVisible.value = true
}

function openCreateDeviceDialog() {
  isEditing.value = false
  currentAppId.value = null
  form.client_name = '授权设备'
  form.redirect_uri = deviceSettings.default_redirect_uri || 'https://oauth.ustb.world/'
  form.set_as_device_shared_client = true
  dialogVisible.value = true
}

function openEditDialog(row) {
  isEditing.value = true
  currentAppId.value = row.app_id
  form.client_name = row.client_name || ''
  form.redirect_uri = row.redirect_uri || ''
  form.set_as_device_shared_client = isDeviceSharedClient(row.app_id)
  dialogVisible.value = true
}

async function submitForm() {
  if (!form.redirect_uri) {
    ElMessage.warning('请填写回调 URL')
    return
  }

  saving.value = true
  try {
    if (isEditing.value && currentAppId.value) {
      await axios.put(`/admin/oauth/apps/${currentAppId.value}`, form, { headers: authHeaders() })
      ElMessage.success('OAuth 应用已更新')
    } else {
      const res = await axios.post('/admin/oauth/apps', form, { headers: authHeaders() })
      newSecret.value = res.data?.client_secret || ''
      if (newSecret.value) secretDialogVisible.value = true
      ElMessage.success('OAuth 应用已创建')
    }
    dialogVisible.value = false
    await loadData()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function saveDeviceSettings() {
  savingDeviceSettings.value = true
  try {
    const payload = {
      shared_client_ids: [...deviceSettings.shared_client_ids],
      expires_in: deviceSettings.expires_in,
      interval: deviceSettings.interval,
      default_redirect_uri: deviceSettings.default_redirect_uri,
    }
    const res = await axios.post('/admin/oauth/device-settings', payload, { headers: authHeaders() })
    Object.assign(deviceSettings, normalizeDeviceSettings(res.data || {}))
    await loadData()
    ElMessage.success('设备授权设置已保存')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    savingDeviceSettings.value = false
  }
}

async function toggleSharedClient(row) {
  try {
    const nextSharedClientIds = isDeviceSharedClient(row.app_id)
      ? deviceSettings.shared_client_ids.filter(item => Number(item) !== Number(row.app_id))
      : [...deviceSettings.shared_client_ids, Number(row.app_id)]
    const res = await axios.post(
      '/admin/oauth/device-settings',
      {
        shared_client_ids: [...new Set(nextSharedClientIds)],
        expires_in: deviceSettings.expires_in,
        interval: deviceSettings.interval,
        default_redirect_uri: deviceSettings.default_redirect_uri,
      },
      { headers: authHeaders() },
    )
    Object.assign(deviceSettings, normalizeDeviceSettings(res.data || {}))
    await loadData()
    ElMessage.success(isDeviceSharedClient(row.app_id) ? `AppID ${row.app_id} 已加入设备授权列表` : `AppID ${row.app_id} 已移出设备授权列表`)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '设置失败')
  }
}

async function resetSecret(row) {
  try {
    await ElMessageBox.confirm(
      `确认重置 AppID ${row.app_id} 的 Secret？旧 Secret 将立即失效。`,
      '确认操作',
      { type: 'warning' },
    )
    const res = await axios.post(`/admin/oauth/apps/${row.app_id}/reset-secret`, {}, { headers: authHeaders() })
    newSecret.value = res.data?.client_secret || ''
    secretDialogVisible.value = true
    ElMessage.success('Secret 已重置')
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.detail || '重置失败')
    }
  }
}

async function removeApp(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除 AppID ${row.app_id}？该应用已有的授权令牌将同时失效。`,
      '危险操作',
      { type: 'warning' },
    )
    await axios.delete(`/admin/oauth/apps/${row.app_id}`, { headers: authHeaders() })
    ElMessage.success('OAuth 应用已删除')
    await loadData()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.detail || '删除失败')
    }
  }
}

async function copySecret() {
  if (!newSecret.value) return
  try {
    await navigator.clipboard.writeText(newSecret.value)
    ElMessage.success('Secret 已复制')
  } catch (e) {
    ElMessage.error('复制失败，请手动复制')
  }
}

onMounted(loadData)
</script>

<style scoped>
@import "@/assets/styles/animations.css";
@import "@/assets/styles/layout.css";
@import "@/assets/styles/cards.css";
@import "@/assets/styles/headers.css";
@import "@/assets/styles/buttons.css";

.oauth-admin-section {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px 0;
}

.card-header-flex {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.meta-label {
  font-size: 12px;
  color: var(--color-text-light);
  margin-bottom: 6px;
}

.mb-6 {
  margin-bottom: 24px;
}

.hint-text {
  margin: 6px 0 0 0;
  font-size: 12px;
  color: var(--color-text-light);
}

.device-settings-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.app-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.form-inline-label {
  margin-left: 10px;
  color: var(--color-text-light);
}

.secret-tip {
  color: var(--el-color-warning-dark-2);
  margin-bottom: 12px;
}

@media (max-width: 900px) {
  .meta-grid {
    grid-template-columns: 1fr;
  }
}
</style>
