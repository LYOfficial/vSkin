<template>
  <div class="settings-section animate-fade-in">
    <div class="page-header">
      <div class="page-header-content">
        <div class="page-header-icon"><Setting /></div>
        <div class="page-header-text">
          <h2>站点设置</h2>
          <p class="subtitle">管理站点基础配置、安全策略及第三方集成</p>
        </div>
      </div>
      <div class="page-header-actions">
        <el-button type="primary" :icon="Refresh" @click="loadAllSettings" class="hover-lift">
          重新加载所有
        </el-button>
      </div>
    </div>

    <!-- Site Config -->
    <el-card class="surface-card mb-6" shadow="never">
      <template #header>
        <div class="card-header-flex">
          <div class="title-group">
            <el-icon><Monitor /></el-icon>
            <span>基础设置</span>
          </div>
          <el-button type="primary" size="small" @click="saveGroup('site')" :loading="saving.site" class="hover-lift">保存</el-button>
        </div>
      </template>
      <el-form label-position="top" :model="settings.site">

        <el-row :gutter="20">
          <el-col :xs="24" :sm="8">
            <el-form-item label="允许新用户注册">
              <el-switch v-model="settings.site.allow_register" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="强制邀请码">
              <el-switch v-model="settings.site.require_invite" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="启用公共皮肤库">
              <el-switch v-model="settings.site.enable_skin_library" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="注册邮箱域名后缀限制">
              <el-select
                v-model="settings.site.register_email_suffixes"
                multiple
                filterable
                allow-create
                default-first-option
                placeholder="例如：example.com、edu.cn"
              />
              <p class="hint-text">留空表示不限制。支持直接输入并回车新增后缀，系统会匹配 @example.com 或 @xxx.example.com。</p>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="最大纹理大小 (KB)">
          <el-input-number v-model="settings.site.max_texture_size" :min="64" :step="128" />
        </el-form-item>
        <el-divider />
        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="站点标题">
              <el-input v-model="settings.site.site_title" placeholder="用于左上角品牌区和首页主标题" />
              <p class="hint-text">站点标题用于站内主视觉展示，建议保持简短醒目。</p>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="站点名称">
              <el-input v-model="settings.site.site_name" placeholder="皮肤站" />
              <p class="hint-text">站点名称用于浏览器标签页标题以及部分对外元信息。</p>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :xs="24" :sm="16">
            <el-form-item label="站点 Logo / Icon 地址">
              <div class="upload-row">
                <el-input v-model="settings.site.site_logo" placeholder="支持在线 URL 或站内相对路径，例如 /static/textures/site-logo.png" />
                <el-upload
                  action="#"
                  :http-request="uploadSiteLogo"
                  :show-file-list="false"
                  accept=".png,.jpg,.jpeg,.webp,.ico,.svg"
                >
                  <el-button type="primary" :icon="Upload" :loading="uploadingLogo">上传图片</el-button>
                </el-upload>
              </div>
              <p class="hint-text">该图片同时用于浏览器图标和菜单栏左上角 Logo。可直接填写 URL，也可点击上传到站内。</p>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="Logo 预览">
              <div class="site-logo-preview" :class="{ empty: !resolvedSiteLogo }">
                <img v-if="resolvedSiteLogo" :src="resolvedSiteLogo" alt="site logo preview" />
                <span v-else>未设置</span>
              </div>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="站点副标题">
              <el-input v-model="settings.site.site_subtitle" placeholder="简洁、高效、现代的 Minecraft 皮肤管理站" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="页脚附加信息">
              <el-input v-model="settings.site.footer_text" placeholder="Copyright © 2026 vSkin" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="24">
            <el-collapse class="regulatory-section" v-model="regulatoryCollapse">
              <el-collapse-item title="监管信息" name="regulatory-info">
                <el-row :gutter="20">
                  <el-col :xs="24" :sm="12">
                    <el-form-item label="ICP 备案信息">
                      <el-input v-model="settings.site.filing_icp" placeholder="留空则不展示" />
                    </el-form-item>
                  </el-col>
                  <el-col :xs="24" :sm="12">
                    <el-form-item label="ICP 备案链接">
                      <el-input v-model="settings.site.filing_icp_link" placeholder="留空则不展示" />
                    </el-form-item>
                  </el-col>
                </el-row>
                <el-row :gutter="20">
                  <el-col :xs="24" :sm="12">
                    <el-form-item label="公安备案信息">
                      <el-input v-model="settings.site.filing_mps" placeholder="留空则不展示" />
                    </el-form-item>
                  </el-col>
                  <el-col :xs="24" :sm="12">
                    <el-form-item label="公安备案链接">
                      <el-input v-model="settings.site.filing_mps_link" placeholder="留空则不展示" />
                    </el-form-item>
                  </el-col>
                </el-row>
              </el-collapse-item>
            </el-collapse>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card class="surface-card mb-6" shadow="never">
      <template #header>
        <div class="card-header-flex">
          <div class="title-group">
            <el-icon><PictureFilled /></el-icon>
            <span>首页图片</span>
          </div>
          <el-button type="primary" size="small" @click="saveGroup('site')" :loading="saving.site">保存</el-button>
        </div>
      </template>
      <el-form label-position="top" :model="settings.site" class="mb-4">
        <el-form-item label="外链图片 URL">
          <el-input
            v-model="settings.site.home_image_urls"
            type="textarea"
            :rows="4"
            placeholder="每行一张图片地址，支持 https://example.com/banner.webp"
          />
          <p class="hint-text">这里配置外部图片地址；下方图库则用于上传站内图片。首页会按配置顺序先展示外链，再展示站内图片。</p>
        </el-form-item>
      </el-form>
      <AdminCarousel embedded />
    </el-card>

    <!-- Security Config -->
    <el-card class="surface-card mb-6" shadow="never">
      <template #header>
        <div class="card-header-flex">
          <div class="title-group">
            <el-icon><Lock /></el-icon>
            <span>安全与速率限制</span>
          </div>
          <el-button type="primary" size="small" @click="saveGroup('security')" :loading="saving.security" class="hover-lift">保存</el-button>
        </div>
      </template>
      <el-form label-position="top" :model="settings.security">
        <el-form-item label="强密码检查">
          <el-switch v-model="settings.security.enable_strong_password_check" />
          <span class="hint-text ml-4">启用后，用户注册或修改密码将执行严格的复杂度检查。</span>
        </el-form-item>
        <el-divider />
        <el-form-item label="身份验证速率限制">
          <el-switch v-model="settings.security.rate_limit_enabled" />
          <span class="hint-text ml-4">启用后将限制登录、重置密码等接口的尝试频率。</span>
        </el-form-item>
        <el-row :gutter="20" v-if="settings.security.rate_limit_enabled">
          <el-col :xs="24" :sm="12">
            <el-form-item label="尝试次数上限">
              <el-input-number v-model="settings.security.rate_limit_auth_attempts" :min="1" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="时间窗口 (分钟)">
              <el-input-number v-model="settings.security.rate_limit_auth_window" :min="1" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- Auth / JWT Config -->
    <el-card class="surface-card mb-6" shadow="never">
      <template #header>
        <div class="card-header-flex">
          <div class="title-group">
            <el-icon><Key /></el-icon>
            <span>令牌与认证 (JWT)</span>
          </div>
          <el-button type="primary" size="small" @click="saveGroup('auth')" :loading="saving.auth" class="hover-lift">保存</el-button>
        </div>
      </template>
      <el-form label-position="top" :model="settings.auth">
        <el-form-item label="令牌有效期 (天)">
          <el-input-number v-model="settings.auth.jwt_expire_days" :min="1" :max="365" />
          <p class="hint-text">用户登录后，其身份令牌将在该天数后失效。</p>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Microsoft Config -->
    <el-card class="surface-card mb-6" shadow="never">
      <template #header>
        <div class="card-header-flex">
          <div class="title-group">
            <el-icon><Link /></el-icon>
            <span>微软正版登录集成</span>
          </div>
          <el-button type="primary" size="small" @click="saveGroup('microsoft')" :loading="saving.microsoft" class="hover-lift">保存</el-button>
        </div>
      </template>
      <el-form label-position="top" :model="settings.microsoft">
        <el-form-item label="Azure Client ID">
          <el-input v-model="settings.microsoft.microsoft_client_id" placeholder="Azure AD 应用 ID" />
        </el-form-item>
        <el-form-item label="Azure Client Secret">
          <el-input v-model="settings.microsoft.microsoft_client_secret" type="password" show-password placeholder="保持空白以不修改" />
        </el-form-item>
        <el-form-item label="Redirect URI">
          <el-input v-model="settings.microsoft.microsoft_redirect_uri" placeholder="https://your-skin-site.com/auth/microsoft/callback" />
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="surface-card mb-6" shadow="never">
      <template #header>
        <div class="card-header-flex">
          <div class="title-group">
            <el-icon><Connection /></el-icon>
            <span>联合认证 / Janus</span>
          </div>
          <el-button type="primary" size="small" @click="saveGroup('janus')" :loading="saving.janus" class="hover-lift">保存</el-button>
        </div>
      </template>
      <el-form label-position="top" :model="settings.janus">
        <el-row :gutter="20">
          <el-col :xs="24" :sm="8">
            <el-form-item label="启用内置 Janus">
              <el-switch v-model="settings.janus.janus_enabled" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="16">
            <el-form-item label="Janus 基础路径">
              <el-input v-model="settings.janus.janus_base_path" placeholder="/api/janus" />
              <p class="hint-text">默认使用 /api/janus，无需额外运行 Janus 服务进程。</p>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="OpenID Issuer (可选)">
          <el-input v-model="settings.janus.janus_issuer" placeholder="留空自动使用 {api_url}{base_path}" />
        </el-form-item>
        <el-divider />
        <el-form-item label="Union API 基址">
          <el-input v-model="settings.janus.janus_union_api_base" placeholder="https://skin.mualliance.ltd/api/union" />
        </el-form-item>
        <el-row :gutter="20">
          <el-col :xs="24" :sm="8">
            <el-form-item label="Union 模式">
              <el-select v-model="settings.janus.janus_union_mode" placeholder="请选择模式">
                <el-option label="全部成员 (all)" value="all" />
                <el-option label="白名单模式 (only)" value="only" />
                <el-option label="黑名单模式 (excludes)" value="excludes" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="16">
            <el-form-item label="Union 代码 (可选)">
              <el-input v-model="settings.janus.janus_union_code" placeholder="例如 SJMC_FDC_MUA" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="自动同步开关">
          <el-switch v-model="settings.janus.janus_union_auto_sync" />
          <span class="hint-text ml-4">预留配置项，便于后续对接 Union 数据同步任务。</span>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, computed } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import AdminCarousel from './AdminCarousel.vue'
import { 
  Refresh, Setting, Monitor, Lock, Key, Link, PictureFilled, Upload, Connection
} from '@element-plus/icons-vue'

const settings = reactive({
  site: {
    site_name: '',
    site_title: '',
    site_logo: '',
    site_subtitle: '',
    home_image_urls: '',
    require_invite: false,
    allow_register: true,
    register_email_suffixes: [],
    enable_skin_library: true,
    max_texture_size: 1024,
    footer_text: '',
    filing_icp: '',
    filing_icp_link: '',
    filing_mps: '',
    filing_mps_link: ''
  },
  security: {
    rate_limit_enabled: true,
    rate_limit_auth_attempts: 5,
    rate_limit_auth_window: 15,
    enable_strong_password_check: false
  },
  auth: {
    jwt_expire_days: 7
  },
  microsoft: {
    microsoft_client_id: '',
    microsoft_client_secret: '',
    microsoft_redirect_uri: ''
  },
  janus: {
    janus_enabled: true,
    janus_base_path: '/api/janus',
    janus_issuer: '',
    janus_union_api_base: 'https://skin.mualliance.ltd/api/union',
    janus_union_mode: 'all',
    janus_union_code: '',
    janus_union_auto_sync: false,
  }
})

const saving = reactive({
  site: false,
  security: false,
  auth: false,
  microsoft: false,
  janus: false,
})

const regulatoryCollapse = ref([])
const uploadingLogo = ref(false)
const resolvedSiteLogo = computed(() => resolveSiteLogo(settings.site.site_logo))

const authHeaders = () => ({ Authorization: 'Bearer ' + localStorage.getItem('jwt') })

function resolveSiteLogo(value) {
  const raw = String(value || '').trim()
  if (!raw) return ''
  if (/^(https?:)?\/\//i.test(raw) || raw.startsWith('data:')) return raw
  if (raw.startsWith('/')) return raw
  const base = import.meta.env.BASE_URL || '/'
  return `${base}${raw}`.replace(/([^:]\/)\/+/g, '$1')
}

async function loadGroup(group) {
  try {
    const res = await axios.get(`/admin/settings/${group}`, { headers: authHeaders() })
    Object.assign(settings[group], res.data)
  } catch (e) {
    ElMessage.error(`加载 ${group} 设置失败`)
  }
}

async function loadAllSettings() {
  await Promise.all([
    loadGroup('site'),
    loadGroup('security'),
    loadGroup('auth'),
    loadGroup('microsoft'),
    loadGroup('janus'),
  ])
}

function broadcastSiteSettings() {
  localStorage.setItem('site_name_cache', settings.site.site_name || '皮肤站')
  localStorage.setItem('site_title_cache', settings.site.site_title || settings.site.site_name || '皮肤站')
  localStorage.setItem('site_logo_cache', settings.site.site_logo || '')
  localStorage.setItem('site_subtitle_cache', settings.site.site_subtitle || '')
  window.dispatchEvent(new CustomEvent('site-settings-updated'))
}

async function uploadSiteLogo({ file }) {
  const formData = new FormData()
  formData.append('file', file)
  uploadingLogo.value = true
  try {
    const res = await axios.post('/admin/site-logo', formData, {
      headers: { ...authHeaders(), 'Content-Type': 'multipart/form-data' }
    })
    settings.site.site_logo = res.data.path || ''
    broadcastSiteSettings()
    ElMessage.success('Logo 上传成功')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || 'Logo 上传失败')
  } finally {
    uploadingLogo.value = false
  }
}

async function saveGroup(group) {
  saving[group] = true
  try {
    await axios.post(`/admin/settings/${group}`, settings[group], { headers: authHeaders() })
    if (group === 'site') broadcastSiteSettings()
    ElMessage.success('设置已更新')
    if (group === 'microsoft') {
       settings.microsoft.microsoft_client_secret = '' // Clear local secret field
    }
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving[group] = false
  }
}

onMounted(loadAllSettings)
</script>

<style scoped>
@import "@/assets/styles/animations.css";
@import "@/assets/styles/layout.css";
@import "@/assets/styles/cards.css";
@import "@/assets/styles/headers.css";
@import "@/assets/styles/buttons.css";

.settings-section {
  max-width: 900px;
  margin: 0 auto;
  padding: 20px 0;
}

.card-header-flex { display: flex; justify-content: space-between; align-items: center; }
.card-header-flex .title-group { display: flex; align-items: center; gap: 8px; font-weight: 600; color: var(--color-heading); }

.settings-group { padding: 10px 0; }
.group-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-light);
  margin-bottom: 20px;
  border-left: 4px solid var(--el-color-primary);
  padding-left: 12px;
}

.hint-text { font-size: 12px; color: var(--color-text-light); line-height: 1.5; margin-top: 4px; display: block; }
.mb-4 { margin-bottom: 16px; }
.mb-6 { margin-bottom: 24px; }
.ml-4 { margin-left: 16px; }

.upload-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.upload-row :deep(.el-upload) {
  flex: 0 0 auto;
}

.upload-row :deep(.el-input) {
  flex: 1 1 auto;
}

.site-logo-preview {
  width: 100%;
  min-height: 92px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-background-soft);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  overflow: hidden;
}

.site-logo-preview img {
  max-width: 100%;
  max-height: 56px;
  object-fit: contain;
}

.site-logo-preview.empty {
  color: var(--color-text-light);
  font-size: 13px;
}

@media (max-width: 768px) {
  .upload-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>