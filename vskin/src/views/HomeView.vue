<script setup>
import { ref, onMounted, inject, computed } from 'vue'
import { useRouter } from 'vue-router'
import { User } from '@element-plus/icons-vue'
import axios from 'axios'

const router = useRouter()
const user = inject('user', ref(null))
const siteName = ref(localStorage.getItem('site_name_cache') || '皮肤站')
const siteSubtitle = ref(localStorage.getItem('site_subtitle_cache') || '简洁、高效、现代的 Minecraft 皮肤管理站')
const isLogged = computed(() => !!user.value || !!localStorage.getItem('jwt'))
const carouselCacheKey = 'home_carousel_cache_v1'
const carouselImages = ref([])

try {
  const cached = localStorage.getItem(carouselCacheKey)
  if (cached) {
    const parsed = JSON.parse(cached)
    if (Array.isArray(parsed) && parsed.length > 0) {
      carouselImages.value = parsed
    }
  }
} catch (e) {
  console.warn('Failed to parse cached carousel:', e)
}

onMounted(async () => {
  try {
    const res = await axios.get('/public/settings')
    if (res.data.site_name) {
      siteName.value = res.data.site_name
      localStorage.setItem('site_name_cache', res.data.site_name)
    }
    if (res.data.site_subtitle) {
      siteSubtitle.value = res.data.site_subtitle
      localStorage.setItem('site_subtitle_cache', res.data.site_subtitle)
    }
  } catch (e) {
    console.warn('Failed to load site settings:', e)
  }

  try {
    const res = await axios.get('/public/carousel')
    if (Array.isArray(res.data)) {
      carouselImages.value = res.data
      localStorage.setItem(carouselCacheKey, JSON.stringify(res.data))
    }
  } catch (e) {
    console.warn('Failed to load carousel images:', e)
  }
})

function goDashboard() { router.push('/dashboard') }
function goLogin() { router.push('/login') }
function goRegister() { router.push('/register') }

function getCarouselUrl(filename) {
  const base = import.meta.env.BASE_URL
  return `${base}static/carousel/${filename}`.replace(/\/+/g, '/')
}
</script>

<template>
  <div class="home-container">
    <!-- Background is FIXED and outside of main content flow -->
    <div v-if="carouselImages.length > 0" class="hero-bg-fixed">
      <el-carousel height="100%" indicator-position="none" arrow="never" :interval="5000">
        <el-carousel-item v-for="img in carouselImages" :key="img">
          <div class="carousel-img-wrap">
            <img :src="getCarouselUrl(img)" class="carousel-img" />
            <div class="carousel-overlay"></div>
          </div>
        </el-carousel-item>
      </el-carousel>
    </div>
    <div v-else class="hero-bg-fixed is-gradient"></div>

    <!-- Main Content -->
    <div class="hero-section">
      <div class="hero-content animate-fade-in">
        <h1 class="hero-title">{{ siteName }}</h1>
        <p class="hero-subtitle">{{ siteSubtitle }}</p>
        <div class="hero-actions">
          <el-button v-if="isLogged" size="large" @click="goDashboard" class="btn-glass btn-glass-primary hero-btn">
            <el-icon><User /></el-icon>
            <span>进入个人面板</span>
          </el-button>
          <template v-else>
            <el-button size="large" @click="goLogin" class="btn-glass btn-glass-primary hero-btn">
              登录账号
            </el-button>
            <el-button size="large" @click="goRegister" class="btn-glass hero-btn">
              即刻注册
            </el-button>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@import "@/assets/styles/animations.css";
@import "@/assets/styles/buttons.css";

.home-container { 
  width: 100%; 
  flex: 1; 
  display: flex; 
  flex-direction: column; 
  position: relative;
  overflow: hidden; /* Prevent any accidental content overflow */
}

/* FIXED Background logic - Using 100% instead of 100vw to avoid scrollbar calculation issues */
.hero-bg-fixed {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: 0;
}
.hero-bg-fixed.is-gradient {
  background: radial-gradient(circle at 0% 0%, #d6e6f5 0%, #ecedf2 42%, #f8f8fb 100%);
}

.hero-bg-fixed :deep(.el-carousel) {
  height: 100%;
}

.carousel-img-wrap { width: 100%; height: 100%; position: relative; }
.carousel-img { width: 100%; height: 100%; object-fit: cover; }
.carousel-overlay { 
  position: absolute; top: 0; left: 0; width: 100%; height: 100%; 
  background: linear-gradient(180deg, rgba(25, 50, 76, 0.32) 0%, rgba(39, 61, 85, 0.18) 40%, rgba(248, 250, 255, 0.42) 100%);
}

.hero-section {
  position: relative;
  z-index: 1;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  padding: 0 20px;
}

.hero-content {
  text-align: center;
  max-width: 860px;
  border: 1px solid rgba(212, 224, 239, 0.92);
  border-radius: 26px;
  background: rgba(246, 250, 255, 0.75);
  backdrop-filter: blur(10px);
  padding: 40px 44px;
  box-shadow: 0 22px 40px rgba(44, 71, 99, 0.18);
}

.hero-title {
  font-size: 56px;
  font-weight: 820;
  margin: 0 0 12px 0;
  letter-spacing: -1.5px;
  color: #1f3f5d;
  text-shadow: none;
}

.hero-subtitle {
  font-size: 20px;
  margin: 0 0 30px 0;
  color: #496887;
  font-weight: 500;
}

.hero-actions { display: flex; gap: 16px; justify-content: center; }
.hero-btn { height: 52px; padding: 0 36px; font-size: 16px; font-weight: 600; border-radius: 8px; }

@media (max-width: 768px) {
  .hero-title { font-size: 36px; }
  .hero-content { padding: 30px 24px; }
  .hero-actions { flex-direction: column; gap: 12px; }
  .hero-btn { width: 100%; }
}
</style>
